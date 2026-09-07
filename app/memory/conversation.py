"""
Gestion de la mémoire de conversation par tenant/utilisateur.

Utilise Redis pour stocker l'historique des conversations avec un TTL.
Chaque conversation est isolée par (tenant_id, user_id, session_id).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import redis

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Stocke et récupère l'historique de conversation dans Redis."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis: redis.Redis | None = None

    @property
    def redis_client(self) -> redis.Redis:
        """Connexion Redis via pool partagé."""
        if self._redis is None:
            self._redis = RedisPool.get_client(self._settings)
        return self._redis

    def _key(self, tenant_id: str, user_id: str, session_id: str = "default") -> str:
        """Clé Redis pour une conversation."""
        return f"evaltask:conv:{tenant_id}:{user_id}:{session_id}"

    def get_history(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str = "default",
        max_messages: int = 20,
    ) -> list[dict]:
        """Récupère l'historique de conversation depuis Redis."""
        key = self._key(tenant_id, user_id, session_id)
        try:
            raw = self.redis_client.lrange(key, -max_messages, -1)
            return [json.loads(msg) for msg in raw]
        except redis.RedisError as exc:
            logger.warning("Redis get_history échoué : %s", exc)
            return []

    def add_message(
        self,
        tenant_id: str,
        user_id: str,
        role: str,
        content: str,
        session_id: str = "default",
        metadata: dict | None = None,
    ) -> None:
        """Ajoute un message à l'historique de conversation."""
        key = self._key(tenant_id, user_id, session_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if metadata:
            message["metadata"] = metadata

        try:
            pipe = self.redis_client.pipeline()
            pipe.rpush(key, json.dumps(message, ensure_ascii=False))
            pipe.ltrim(key, -self._settings.conversation_max_messages, -1)
            pipe.expire(key, self._settings.conversation_ttl_seconds)
            pipe.execute()
        except redis.RedisError as exc:
            logger.warning("Redis add_message échoué : %s", exc)

    def clear_history(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str = "default",
    ) -> None:
        """Supprime l'historique de conversation."""
        key = self._key(tenant_id, user_id, session_id)
        try:
            self.redis_client.delete(key)
        except redis.RedisError as exc:
            logger.warning("Redis clear_history échoué : %s", exc)

    def add_feedback(
        self,
        tenant_id: str,
        user_id: str,
        message_index: int,
        feedback: str,  # "positive" | "negative"
        session_id: str = "default",
    ) -> None:
        """
        Stocke le feedback utilisateur sur un message.
        Utilisé pour l'apprentissage et l'amélioration du RAG.
        """
        feedback_key = f"evaltask:feedback:{tenant_id}"
        entry = {
            "user_id": user_id,
            "session_id": session_id,
            "message_index": message_index,
            "feedback": feedback,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            self.redis_client.rpush(feedback_key, json.dumps(entry, ensure_ascii=False))
            self.redis_client.expire(feedback_key, 86400 * 30)  # 30 jours
        except redis.RedisError as exc:
            logger.warning("Redis add_feedback échoué : %s", exc)
