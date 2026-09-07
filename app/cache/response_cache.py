"""
Cache de réponses LLM dans Redis.

Évite les appels LLM redondants en mettant en cache les réponses
basées sur un hash de (tenant_id + message + contexte + modèle).

Principes :
- LLMOps Engineer : réduction coûts, latence, hit/miss metrics
- LangChain Backend Engineer : invalidation par tenant, TTL configurable
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.config import Settings, get_settings
from app.observability.metrics import MetricsCollector
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Cache de réponses LLM dans Redis.

    Clé Redis : evaltask:cache:{tenant_id}:{hash}
    Hash = SHA-256(tenant_id + message + user_context + page_context + model + tool_results)

    Métriques :
    - evaltask:cache:{tenant_id}:hits  (compteur)
    - evaltask:cache:{tenant_id}:misses (compteur)
    """

    _instance: ResponseCache | None = None

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> ResponseCache:
        if cls._instance is None:
            cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = RedisPool.get_client(settings)
        self._ttl = self._settings.cache_ttl_seconds
        self._enabled = self._settings.cache_enabled
        self._metrics = MetricsCollector.get_instance()

    def _compute_hash(
        self,
        tenant_id: str,
        message: str,
        user_context: dict | None,
        page_context: dict | None,
        model: str,
        tool_results: list[dict] | None,
    ) -> str:
        """Calcule un hash stable pour la requête."""
        payload = json.dumps(
            {
                "t": tenant_id,
                "m": message or "",
                "u": user_context or {},
                "p": page_context or {},
                "model": model,
                "tr": tool_results or [],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _redis_key(self, tenant_id: str, cache_hash: str) -> str:
        return f"evaltask:cache:{tenant_id}:{cache_hash}"

    def get(
        self,
        tenant_id: str,
        message: str,
        user_context: dict | None = None,
        page_context: dict | None = None,
        model: str = "",
        tool_results: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        """
        Tente de récupérer une réponse en cache.
        Retourne None si absent ou cache désactivé.
        """
        if not self._enabled:
            return None

        cache_hash = self._compute_hash(tenant_id, message, user_context, page_context, model, tool_results)
        key = self._redis_key(tenant_id, cache_hash)

        try:
            raw = self._redis.get(key)
            if raw:
                self._redis.hincrby(f"evaltask:cache:{tenant_id}:stats", "hits", 1)
                self._metrics.record_cache_hit(tenant_id)
                logger.debug("[%s] Cache HIT (hash=%s)", tenant_id, cache_hash[:12])
                return json.loads(raw)
        except Exception as exc:
            logger.warning("[%s] Cache get failed: %s", tenant_id, exc)

        try:
            self._redis.hincrby(f"evaltask:cache:{tenant_id}:stats", "misses", 1)
        except Exception:
            pass
        self._metrics.record_cache_miss(tenant_id)
        logger.debug("[%s] Cache MISS (hash=%s)", tenant_id, cache_hash[:12])
        return None

    def set(
        self,
        tenant_id: str,
        message: str,
        response: dict[str, Any],
        user_context: dict | None = None,
        page_context: dict | None = None,
        model: str = "",
        tool_results: list[dict] | None = None,
    ) -> None:
        """Stocke une réponse en cache."""
        if not self._enabled:
            return

        # Ne pas cacher les erreurs ni les tool_calls (doivent être exécutés)
        if response.get("error"):
            return
        if response.get("tool_calls"):
            return

        cache_hash = self._compute_hash(tenant_id, message, user_context, page_context, model, tool_results)
        key = self._redis_key(tenant_id, cache_hash)

        try:
            self._redis.setex(key, self._ttl, json.dumps(response, ensure_ascii=False))
            logger.debug("[%s] Cache SET (hash=%s, ttl=%ds)", tenant_id, cache_hash[:12], self._ttl)
        except Exception as exc:
            logger.warning("[%s] Cache set failed: %s", tenant_id, exc)

    def invalidate_tenant(self, tenant_id: str) -> int:
        """Invalide tout le cache d'un tenant. Retourne le nombre de clés supprimées."""
        count = 0
        try:
            for key in self._redis.scan_iter(f"evaltask:cache:{tenant_id}:*"):
                self._redis.delete(key)
                count += 1
            self._redis.delete(f"evaltask:cache:{tenant_id}:stats")
            logger.info("[%s] Cache invalidé (%d clés supprimées)", tenant_id, count)
        except Exception as exc:
            logger.warning("[%s] Cache invalidation failed: %s", tenant_id, exc)
        return count

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        """Retourne les statistiques de cache pour un tenant."""
        try:
            stats = self._redis.hgetall(f"evaltask:cache:{tenant_id}:stats")
            hits = int(stats.get("hits", 0))
            misses = int(stats.get("misses", 0))
            total = hits + misses
            hit_rate = round(hits / total * 100, 2) if total > 0 else 0.0

            # Compter les clés en cache
            key_count = sum(1 for _ in self._redis.scan_iter(f"evaltask:cache:{tenant_id}:*"))

            return {
                "tenant_id": tenant_id,
                "hits": hits,
                "misses": misses,
                "hit_rate_pct": hit_rate,
                "cached_entries": key_count,
                "ttl_seconds": self._ttl,
                "enabled": self._enabled,
            }
        except Exception as exc:
            logger.warning("[%s] Cache stats failed: %s", tenant_id, exc)
            return {
                "tenant_id": tenant_id,
                "hits": 0,
                "misses": 0,
                "hit_rate_pct": 0.0,
                "cached_entries": 0,
                "ttl_seconds": self._ttl,
                "enabled": self._enabled,
            }
