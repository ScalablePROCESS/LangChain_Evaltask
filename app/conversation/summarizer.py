"""
Résumé automatique d'historique de conversation.

Après N messages, l'historique est résumé par le LLM pour préserver le contexte
tout en réduisant le nombre de tokens envoyés. Le résumé est mis en cache dans Redis.

Principes :
- LangChain Solution Architect : préservation du contexte, réduction de tokens
- LLMOps Engineer : cache du résumé, métriques
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Tu es un assistant de synthèse de conversation. Résume la conversation suivante de manière concise et structurée.

Conserve :
- Les sujets abordés et décisions prises
- Les données chiffrées mentionnées (montants, dates, codes)
- Les outils demandés et leurs résultats
- Le contexte métier (projet, phase, entité)

Format : 5-10 lignes maximum, en français, sans introduction ni conclusion.

Conversation à résumer :
"""


class ConversationSummarizer:
    """
    Résume l'historique de conversation après un seuil de messages.

    - Cache le résumé dans Redis (par session)
    - Invalide le cache si l'historique change
    - Utilise le LLM principal pour générer le résumé
    """

    _instance: ConversationSummarizer | None = None

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> ConversationSummarizer:
        if cls._instance is None:
            cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = RedisPool.get_client(settings)
        self._summary_threshold = self._settings.summary_threshold_messages
        self._keep_recent = self._settings.summary_keep_recent_messages

    def _redis_key(self, tenant_id: str, session_id: str) -> str:
        return f"evaltask:summary:{tenant_id}:{session_id}"

    def _compute_history_hash(self, history: list[dict]) -> str:
        """Hash de l'historique pour détecter les changements."""
        payload = json.dumps(history, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def needs_summary(self, history: list[dict] | None) -> bool:
        """Vérifie si l'historique dépasse le seuil de résumé."""
        if not history:
            return False
        return len(history) >= self._summary_threshold

    async def get_or_create_summary(
        self,
        history: list[dict],
        tenant_id: str,
        session_id: str,
        llm,
        request_id: str | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Retourne (résumé, messages récents à conserver).

        Si un résumé en cache correspond à l'historique actuel, il est réutilisé.
        Sinon, un nouveau résumé est généré via le LLM.

        Les `self._keep_recent` derniers messages sont conservés tels quels
        après le résumé pour maintenir le contexte immédiat.
        """
        if not self.needs_summary(history):
            return "", history

        history_hash = self._compute_history_hash(history)
        cache_key = self._redis_key(tenant_id, session_id)

        # Vérifier le cache
        try:
            cached = self._redis.hgetall(cache_key)
            if cached and cached.get("hash") == history_hash:
                logger.debug("[%s] Résumé de conversation réutilisé depuis cache", request_id)
                summary = cached.get("summary", "")
                recent = history[-self._keep_recent :]
                return summary, recent
        except Exception as exc:
            logger.warning("[%s] Cache résumé inaccessible: %s", request_id, exc)

        # Messages à résumer (tout sauf les N plus récents)
        to_summarize = history[: -self._keep_recent]
        recent = history[-self._keep_recent :]

        # Construire le texte à résumer
        conversation_text = self._format_history_for_summary(to_summarize)

        # Appel LLM pour le résumé
        try:
            summary_messages = [
                SystemMessage(content=SUMMARY_PROMPT),
                HumanMessage(content=conversation_text),
            ]
            response: AIMessage = await llm.ainvoke(summary_messages)
            summary = response.content.strip()

            # Mettre en cache
            try:
                self._redis.hset(
                    cache_key,
                    mapping={
                        "hash": history_hash,
                        "summary": summary,
                        "created_at": str(time.time()),
                        "message_count": str(len(to_summarize)),
                    },
                )
                self._redis.expire(cache_key, self._settings.conversation_ttl_seconds)
            except Exception as exc:
                logger.warning("[%s] Cache résumé échec écriture: %s", request_id, exc)

            logger.info(
                "[%s] Résumé généré (%d messages → %d chars)",
                request_id,
                len(to_summarize),
                len(summary),
            )
            return summary, recent

        except Exception as exc:
            logger.warning("[%s] Résumé LLM échoué: %s — utilisation historique tronqué", request_id, exc)
            # Fallback : garder les N derniers messages sans résumé
            return "", recent

    def _format_history_for_summary(self, history: list[dict]) -> str:
        """Formate l'historique en texte pour le résumé."""
        lines = []
        for entry in history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "tool_results":
                if isinstance(content, list):
                    for tr in content:
                        lines.append(f"Outil ({tr.get('tool_name', 'inconnu')}): {tr.get('result', '')}")
                else:
                    lines.append(f"Outil: {content}")
            else:
                lines.append(f"Utilisateur: {content}")
        return "\n".join(lines)

    def invalidate(self, tenant_id: str, session_id: str) -> None:
        """Invalide le résumé en cache pour une session."""
        self._redis.delete(self._redis_key(tenant_id, session_id))
