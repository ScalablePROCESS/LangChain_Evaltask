"""
Endpoints de gestion des clés API OpenRouter par tenant.

Permet à chaque plateforme EvalTask d'enregistrer sa clé OpenRouter
côté serveur (chiffrée dans Redis) plutôt que de l'envoyer à chaque requête.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.api_key_manager import APIKeyManager
from app.auth.jwt_auth import TenantInfo, verify_tenant_token
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["keys"])


class StoreKeyRequest(BaseModel):
    """Requête d'enregistrement d'une clé API."""

    tenant_id: str
    openrouter_api_key: str


class KeyStatusResponse(BaseModel):
    """Statut de la clé API d'un tenant."""

    tenant_id: str
    has_key: bool


class KeyActionResponse(BaseModel):
    """Réponse générique d'action sur clé."""

    status: str
    tenant_id: str


@router.post("/api/v1/keys", response_model=KeyActionResponse)
async def store_api_key(
    request: StoreKeyRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> KeyActionResponse:
    """
    Enregistre (ou met à jour) la clé API OpenRouter d'un tenant.
    La clé est chiffrée avant stockage dans Redis.
    """
    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if not request.openrouter_api_key or not request.openrouter_api_key.startswith("sk-"):
        raise HTTPException(status_code=422, detail="Clé API invalide (format attendu : sk-...).")

    manager = APIKeyManager.get_instance(settings)
    manager.store_key(request.tenant_id, request.openrouter_api_key)

    logger.info("[%s] Clé API enregistrée", request.tenant_id)

    return KeyActionResponse(status="ok", tenant_id=request.tenant_id)


@router.get("/api/v1/keys/{tenant_id}", response_model=KeyStatusResponse)
async def get_key_status(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> KeyStatusResponse:
    """Vérifie si une clé API est enregistrée pour un tenant (ne révèle pas la clé)."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    manager = APIKeyManager.get_instance(settings)
    has_key = manager.has_key(tenant_id)

    return KeyStatusResponse(tenant_id=tenant_id, has_key=has_key)


@router.delete("/api/v1/keys/{tenant_id}", response_model=KeyActionResponse)
async def delete_api_key(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> KeyActionResponse:
    """Supprime la clé API d'un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    manager = APIKeyManager.get_instance(settings)
    manager.delete_key(tenant_id)

    logger.info("[%s] Clé API supprimée", tenant_id)

    return KeyActionResponse(status="ok", tenant_id=tenant_id)
