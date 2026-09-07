"""
Endpoints de gestion du cache de réponses LLM.

Permet de consulter les statistiques de cache et d'invalider
le cache par tenant.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt_auth import TenantInfo, verify_tenant_token
from app.cache.response_cache import ResponseCache
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cache"])


class CacheStatsResponse(BaseModel):
    tenant_id: str
    hits: int
    misses: int
    hit_rate_pct: float
    cached_entries: int
    ttl_seconds: int
    enabled: bool


class CacheInvalidateResponse(BaseModel):
    tenant_id: str
    invalidated_keys: int


@router.get("/api/v1/cache/{tenant_id}/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> CacheStatsResponse:
    """Statistiques de cache pour un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    cache = ResponseCache.get_instance(settings)
    stats = cache.get_stats(tenant_id)

    return CacheStatsResponse(**stats)


@router.delete("/api/v1/cache/{tenant_id}", response_model=CacheInvalidateResponse)
async def invalidate_cache(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> CacheInvalidateResponse:
    """Invalide tout le cache de réponses d'un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    cache = ResponseCache.get_instance(settings)
    count = cache.invalidate_tenant(tenant_id)

    return CacheInvalidateResponse(tenant_id=tenant_id, invalidated_keys=count)
