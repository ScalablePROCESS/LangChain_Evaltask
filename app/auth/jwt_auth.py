"""
Authentification JWT pour les plateformes EvalTask (tenants).

Principes appliqués :
- AI Security & Compliance : vérification stricte, audit, rate limiting
- LangChain Backend Engineer : contrats typés, traçabilité
- API Designer : codes HTTP cohérents, erreurs non ambiguës
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import jwt
import redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


@dataclass
class TenantInfo:
    """Informations extraites et validées du JWT d'un tenant."""

    tenant_id: str
    claims: dict[str, Any] = field(default_factory=dict)
    authenticated_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"TenantInfo(tenant_id={self.tenant_id!r})"


def _check_rate_limit(tenant_id: str, settings: Settings) -> None:
    """
    Vérifie le rate limit par tenant via Redis.
    Lève HTTPException 429 si dépassé.
    """
    try:
        r = RedisPool.get_client()
        key = f"evaltask:ratelimit:{tenant_id}:{int(time.time()) // 60}"
        current = r.incr(key)
        if current == 1:
            r.expire(key, 120)
        if current > settings.rate_limit_requests_per_minute:
            logger.warning(
                "[auth] Rate limit exceeded for tenant %s (%d/%d)",
                tenant_id,
                current,
                settings.rate_limit_requests_per_minute,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de requêtes dépassée. Réessayez dans quelques instants.",
                headers={"Retry-After": "60"},
            )
    except redis.RedisError as exc:
        if settings.rate_limit_fail_open:
            logger.warning("[auth] Redis rate limit check failed: %s (allowing request)", exc)
        else:
            logger.error("[auth] Redis rate limit check failed: %s (blocking request)", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service de rate limiting indisponible. Réessayez dans quelques instants.",
            )


def check_embed_rate_limit(tenant_id: str, settings: Settings) -> None:
    """
    Vérifie le rate limit pour les endpoints d'embedding (plus restrictif).
    À appeler manuellement dans les endpoints /api/v1/embed/*.
    """
    try:
        r = RedisPool.get_client()
        key = f"evaltask:ratelimit:embed:{tenant_id}:{int(time.time()) // 60}"
        current = r.incr(key)
        if current == 1:
            r.expire(key, 120)
        if current > settings.rate_limit_embed_per_minute:
            logger.warning(
                "[auth] Embed rate limit exceeded for tenant %s (%d/%d)",
                tenant_id,
                current,
                settings.rate_limit_embed_per_minute,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite d'ingestion dépassée. Réessayez dans quelques instants.",
                headers={"Retry-After": "60"},
            )
    except redis.RedisError as exc:
        if settings.rate_limit_fail_open:
            logger.warning("[auth] Redis embed rate limit check failed: %s (allowing request)", exc)
        else:
            logger.error("[auth] Redis embed rate limit check failed: %s (blocking request)", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service de rate limiting indisponible. Réessayez dans quelques instants.",
            )


# Clés de métadonnées autorisées dans ChromaDB
_ALLOWED_METADATA_KEYS = {
    "source",
    "source_type",
    "category",
    "tenant_id",
    "filename",
    "source_name",
    "page",
    "chunk_index",
}

# Valeurs max pour éviter les abus
_MAX_METADATA_VALUE_LENGTH = 500


def sanitize_metadata(metadata: dict) -> dict:
    """
    Nettoie et valide les métadonnées avant stockage dans ChromaDB.
    - Filtre les clés non autorisées
    - Limite la taille des valeurs
    - Supprime les valeurs None
    """
    if not metadata:
        return {}

    cleaned = {}
    for key, value in metadata.items():
        if key not in _ALLOWED_METADATA_KEYS:
            logger.debug("[auth] Métadonnée '%s' filtrée (non autorisée)", key)
            continue
        if value is None:
            continue
        str_value = str(value)
        if len(str_value) > _MAX_METADATA_VALUE_LENGTH:
            str_value = str_value[:_MAX_METADATA_VALUE_LENGTH]
            logger.debug("[auth] Métadonnée '%s' tronquée (trop longue)", key)
        cleaned[key] = str_value

    return cleaned


def _get_client_ip(request: Request) -> str:
    """Extrait l'IP du client en tenant compte des proxies (X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — on prend le premier
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def verify_tenant_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> TenantInfo:
    """
    Décode et vérifie le JWT envoyé par une plateforme EvalTask.
    Applique rate limiting et journalise l'accès.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            leeway=settings.jwt_expiry_leeway_seconds,
        )
    except jwt.ExpiredSignatureError:
        logger.warning("[auth] Expired token from %s", _get_client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré. La plateforme doit regénérer un JWT.",
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("[auth] Invalid token from %s: %s", _get_client_ip(request), exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide.",
        )

    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Le token ne contient pas de tenant_id.",
        )

    # Rate limiting par tenant
    _check_rate_limit(tenant_id, settings)

    # Audit log (pas de données sensibles)
    logger.info(
        "[auth] Tenant %s authenticated from %s",
        tenant_id,
        _get_client_ip(request),
    )

    return TenantInfo(tenant_id=tenant_id, claims=payload)
