"""
Système de feedback sur les réponses de l'assistant.

Permet aux utilisateurs de donner un thumbs up/down et un commentaire
sur les réponses de l'IA. Stocké dans Redis pour analyse ultérieure.

Principes :
- LLMOps Engineer : données pour amélioration continue, évaluation qualité
- AI Security & Compliance : isolation par tenant, pas de données sensibles
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)


class FeedbackStore:
    """
    Stockage des feedbacks utilisateurs dans Redis.

    Structure :
    - evaltask:feedback:{tenant_id}:log  → list (derniers 500 feedbacks)
    - evaltask:feedback:{tenant_id}:stats → hash (thumbs_up, thumbs_down, total)
    """

    _instance: FeedbackStore | None = None

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> FeedbackStore:
        if cls._instance is None:
            cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = RedisPool.get_client(settings)

    def record_feedback(
        self,
        tenant_id: str,
        request_id: str,
        rating: str,
        comment: str | None = None,
        user_id: str | None = None,
        message: str | None = None,
        reply: str | None = None,
        model_used: str | None = None,
    ) -> dict[str, Any]:
        """
        Enregistre un feedback utilisateur.

        Args:
            rating: "up" ou "down"
        """
        if rating not in ("up", "down"):
            raise ValueError("rating doit être 'up' ou 'down'")

        entry = {
            "request_id": request_id,
            "rating": rating,
            "comment": comment,
            "user_id": user_id,
            "message_preview": (message[:200] if message else None),
            "reply_preview": (reply[:200] if reply else None),
            "model_used": model_used,
            "timestamp": time.time(),
        }

        pipe = self._redis.pipeline()

        # Log circulaire (500 derniers)
        log_key = f"evaltask:feedback:{tenant_id}:log"
        pipe.lpush(log_key, json.dumps(entry, ensure_ascii=False))
        pipe.ltrim(log_key, 0, 499)
        pipe.expire(log_key, 90 * 24 * 3600)  # 90 jours

        # Compteurs
        stats_key = f"evaltask:feedback:{tenant_id}:stats"
        if rating == "up":
            pipe.hincrby(stats_key, "thumbs_up", 1)
        else:
            pipe.hincrby(stats_key, "thumbs_down", 1)
        pipe.hincrby(stats_key, "total", 1)

        pipe.execute()

        logger.info("[%s] Feedback %s pour request %s", tenant_id, rating, request_id)

        return {"status": "ok", "rating": rating}

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        """Retourne les statistiques de feedback pour un tenant."""
        stats_key = f"evaltask:feedback:{tenant_id}:stats"
        data = self._redis.hgetall(stats_key)

        thumbs_up = int(data.get("thumbs_up", 0))
        thumbs_down = int(data.get("thumbs_down", 0))
        total = int(data.get("total", 0))

        satisfaction_rate = round(thumbs_up / total * 100, 2) if total > 0 else 0.0

        return {
            "tenant_id": tenant_id,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "total": total,
            "satisfaction_rate_pct": satisfaction_rate,
        }

    def get_recent(self, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retourne les derniers feedbacks d'un tenant."""
        log_key = f"evaltask:feedback:{tenant_id}:log"
        raw_entries = self._redis.lrange(log_key, 0, limit - 1)

        feedbacks = []
        for raw in raw_entries:
            try:
                feedbacks.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

        return feedbacks

    def get_negative_feedbacks(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Retourne les feedbacks négatifs (pour analyse qualité)."""
        all_feedbacks = self.get_recent(tenant_id, limit * 3)
        return [f for f in all_feedbacks if f.get("rating") == "down"][:limit]
