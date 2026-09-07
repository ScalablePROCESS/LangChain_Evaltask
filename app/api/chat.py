"""
Endpoint principal de chat pour les plateformes EvalTask.

Principes appliqués :
- API Designer : contrats typés, erreurs structurées, codes HTTP cohérents
- LangChain Backend Engineer : corrélation request_id, observabilité
- AI Security & Compliance : validation entrée, masquage clé API dans logs
- LLMOps Engineer : métriques durée/modèle, traçabilité

Flux :
1. Rails envoie message + contexte utilisateur + clé OpenRouter
2. LangChain orchestre LLM avec RAG et tool calling
3. Si tool_calls → renvoie à Rails pour exécution locale
4. Rails exécute les outils et renvoie les résultats
5. LangChain finalise la réponse
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.api_key_manager import APIKeyManager
from app.auth.jwt_auth import TenantInfo, verify_tenant_token
from app.chains.evaltask_chain import EvalTaskChain
from app.config import Settings, get_settings
from app.memory.conversation import ConversationMemory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# Mémoire de conversation partagée (singleton lazy)
_conversation_memory: ConversationMemory | None = None


def get_conversation_memory(settings: Settings | None = None) -> ConversationMemory:
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory(settings)
    return _conversation_memory


# ─── Modèles de requête / réponse ───


class UserContext(BaseModel):
    """Contexte utilisateur envoyé par la plateforme Rails."""

    name: str = "Utilisateur"
    roles: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    user_id: str | None = None


class PageContext(BaseModel):
    """Contexte de la page actuelle sur la plateforme."""

    entity_type: str | None = None
    entity_code: str | None = None
    entity_name: str | None = None
    page_title: str | None = None
    page_path: str | None = None


class ToolResult(BaseModel):
    """Résultat d'un outil exécuté côté Rails."""

    tool_call_id: str
    name: str
    result: Any


class ChatRequest(BaseModel):
    """Requête de chat envoyée par une plateforme EvalTask."""

    message: str | None = Field(None, description="Message utilisateur. Requis sauf si tool_results est fourni.")
    conversation_history: list[dict] = Field(
        default_factory=list,
        description="Historique de conversation (liste de {role, content}). Limité à 50 messages.",
    )
    user_context: UserContext = Field(
        default_factory=UserContext, description="Contexte utilisateur (nom, rôles, modules)."
    )
    page_context: PageContext | None = Field(None, description="Contexte de la page courante sur la plateforme.")
    tenant_id: str = Field(..., description="Identifiant du tenant (doit correspondre au JWT).")
    openrouter_api_key: str | None = Field(
        None,
        description="Clé API OpenRouter. Optionnel si la clé est stockée côté serveur via /api/v1/keys.",
    )
    model: str | None = Field(None, description="Modèle LLM à utiliser. Par défaut: openrouter_default_model.")
    session_id: str = Field("default", description="Identifiant de session pour la mémoire de conversation.")
    request_id: str | None = Field(None, description="Identifiant de corrélation. Généré automatiquement si absent.")
    tool_results: list[ToolResult] | None = Field(
        None,
        description="Résultats d'outils exécutés côté Rails (tour de tool calling).",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Quel est le budget du projet PRJ-001 ?",
                "tenant_id": "acme-corp",
                "user_context": {
                    "name": "Alice Dupont",
                    "roles": ["pm_direction"],
                    "modules": ["projects", "costs"],
                },
                "session_id": "sess-abc123",
            }
        }
    }


class ToolCallOut(BaseModel):
    """Outil que Rails doit exécuter localement."""

    id: str
    name: str
    arguments: dict


class ChatResponse(BaseModel):
    """Réponse du serveur LangChain."""

    reply: str | None = Field(None, description="Réponse texte de l'assistant. Null si tool_calls est non vide.")
    tool_calls: list[ToolCallOut] = Field(default_factory=list, description="Outils à exécuter côté Rails.")
    error: str | None = Field(None, description="Message d'erreur si la requête a échoué.")
    model_used: str | None = Field(
        None, description="Modèle LLM réellement utilisé (peut différer en cas de fallback)."
    )
    tenant_id: str | None = Field(None, description="Identifiant du tenant.")
    request_id: str | None = Field(None, description="Identifiant de corrélation.")
    duration_ms: int | None = Field(None, description="Durée de traitement en millisecondes.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "reply": "Le budget du projet PRJ-001 est de 15 000 000 FCFA...",
                "tool_calls": [],
                "error": None,
                "model_used": "z-ai/glm-5.2",
                "tenant_id": "acme-corp",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "duration_ms": 1234,
            }
        }
    }


# ─── Endpoint ───


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """
    Point d'entrée principal du chat IA.

    Appelé par chaque plateforme EvalTask déployée.
    L'authentification se fait par JWT signé par la plateforme.
    La clé OpenRouter est propre à chaque plateforme (isolation des coûts).
    """
    request_id = request.request_id or str(uuid.uuid4())

    # Vérifier que le tenant_id du JWT correspond à celui de la requête
    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Le tenant_id du token ne correspond pas à la requête.",
        )

    if not request.message and not request.tool_results:
        raise HTTPException(
            status_code=422,
            detail="Le message ou les résultats d'outils sont requis.",
        )

    logger.info(
        "[%s][%s] Chat request user=%s message_len=%d tool_results=%d",
        request_id,
        request.tenant_id,
        request.user_context.name,
        len(request.message or ""),
        len(request.tool_results or []),
    )

    # Récupérer la clé API (serveur d'abord, fallback sur la requête)
    api_key_manager = APIKeyManager.get_instance(settings)
    api_key = api_key_manager.get_key(
        tenant_id=request.tenant_id,
        fallback=request.openrouter_api_key,
    )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Aucune clé API OpenRouter configurée pour ce tenant. "
            "Utilisez POST /api/v1/keys pour enregistrer une clé.",
        )

    # Construire la chaîne LangChain
    chain = EvalTaskChain(
        tenant_id=request.tenant_id,
        openrouter_api_key=api_key,
        user_context=request.user_context.model_dump(),
        model=request.model,
        settings=settings,
        request_id=request_id,
    )

    # Préparer les résultats d'outils si présents
    tool_results_data = None
    if request.tool_results:
        tool_results_data = [tr.model_dump() for tr in request.tool_results]

    # Invoquer la chaîne
    result = await chain.invoke(
        message=request.message,
        history=request.conversation_history,
        page_context=request.page_context.model_dump() if request.page_context else None,
        tool_results=tool_results_data,
    )

    # Stocker dans la mémoire de conversation si réponse finale
    if result.get("reply") and request.user_context.user_id:
        try:
            memory = get_conversation_memory(settings)
            if request.message:
                memory.add_message(
                    tenant_id=request.tenant_id,
                    user_id=request.user_context.user_id,
                    role="user",
                    content=request.message,
                    session_id=request.session_id,
                    metadata={"request_id": request_id},
                )
            memory.add_message(
                tenant_id=request.tenant_id,
                user_id=request.user_context.user_id,
                role="assistant",
                content=result["reply"],
                session_id=request.session_id,
                metadata={
                    "request_id": request_id,
                    "model_used": result.get("model_used"),
                },
            )
        except Exception as exc:
            logger.warning("[%s] Échec stockage mémoire : %s", request_id, exc)

    return ChatResponse(
        reply=result.get("reply"),
        tool_calls=[ToolCallOut(**tc) for tc in result.get("tool_calls", [])],
        error=result.get("error"),
        model_used=result.get("model_used") or request.model or settings.openrouter_default_model,
        tenant_id=request.tenant_id,
        request_id=request_id,
        duration_ms=result.get("duration_ms"),
    )


# ─── Endpoint SSE streaming ───


@router.post("/api/v1/chat/stream")
async def chat_stream(
    request: ChatRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Chat IA en streaming Server-Sent Events.

    Émet des événements SSE au format :
    - data: {"type": "token", "content": "..."}\n\n  — fragment de texte
    - data: {"type": "tool_calls", "tool_calls": [...]}\n\n  — outils à exécuter
    - data: {"type": "done", "model_used": "...", "duration_ms": ...}\n\n  — fin
    - data: {"type": "error", "error": "..."}\n\n  — erreur
    """
    request_id = request.request_id or str(uuid.uuid4())

    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Le tenant_id du token ne correspond pas à la requête.",
        )

    if not request.message and not request.tool_results:
        raise HTTPException(
            status_code=422,
            detail="Le message ou les résultats d'outils sont requis.",
        )

    logger.info(
        "[%s][%s] Chat stream request user=%s message_len=%d tool_results=%d",
        request_id,
        request.tenant_id,
        request.user_context.name,
        len(request.message or ""),
        len(request.tool_results or []),
    )

    # Récupérer la clé API (serveur d'abord, fallback sur la requête)
    api_key_manager = APIKeyManager.get_instance(settings)
    api_key = api_key_manager.get_key(
        tenant_id=request.tenant_id,
        fallback=request.openrouter_api_key,
    )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Aucune clé API OpenRouter configurée pour ce tenant.",
        )

    chain = EvalTaskChain(
        tenant_id=request.tenant_id,
        openrouter_api_key=api_key,
        user_context=request.user_context.model_dump(),
        model=request.model,
        settings=settings,
        request_id=request_id,
    )

    tool_results_data = None
    if request.tool_results:
        tool_results_data = [tr.model_dump() for tr in request.tool_results]

    async def event_generator():
        full_reply = ""
        model_used = None
        should_store = False

        async for event in chain.astream(
            message=request.message,
            history=request.conversation_history,
            page_context=request.page_context.model_dump() if request.page_context else None,
            tool_results=tool_results_data,
        ):
            event_type = event.get("type")

            if event_type == "token":
                full_reply += event.get("content", "")
                should_store = True

            if event_type == "done":
                model_used = event.get("model_used")
                full_reply = event.get("full_reply", full_reply)

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Stocker en mémoire après la fin du stream
        if should_store and full_reply and request.user_context.user_id:
            try:
                memory = get_conversation_memory(settings)
                if request.message:
                    memory.add_message(
                        tenant_id=request.tenant_id,
                        user_id=request.user_context.user_id,
                        role="user",
                        content=request.message,
                        session_id=request.session_id,
                        metadata={"request_id": request_id},
                    )
                memory.add_message(
                    tenant_id=request.tenant_id,
                    user_id=request.user_context.user_id,
                    role="assistant",
                    content=full_reply,
                    session_id=request.session_id,
                    metadata={
                        "request_id": request_id,
                        "model_used": model_used,
                    },
                )
            except Exception as exc:
                logger.warning("[%s] Échec stockage mémoire (stream) : %s", request_id, exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
