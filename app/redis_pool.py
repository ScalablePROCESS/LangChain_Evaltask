"""
Pool de connexions Redis partagé pour tous les modules.

Au lieu que chaque module crée sa propre connexion redis.from_url(),
tous utilisent un pool unique via RedisPool.get_client().

Bénéfices :
- Réduction de la latence (connexions réutilisées)
- Contrôle du nombre de connexions (max_connections)
- Health check centralisé
- Configuration uniforme (decode_responses, retry, timeout)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import redis

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RedisPool:
    """
    Pool de connexions Redis singleton.

    Utilise redis.ConnectionPool sous le hood.
    Tous les modules appellent RedisPool.get_client() pour obtenir
    une connexion partagée depuis le pool.
    """

    _instance: RedisPool | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> RedisPool:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._pool = redis.ConnectionPool.from_url(
            self._settings.redis_url,
            decode_responses=True,
            max_connections=self._settings.redis_max_connections,
            socket_connect_timeout=self._settings.redis_socket_timeout,
            socket_keepalive=True,
            socket_keepalive_options={},
            retry_on_timeout=True,
            health_check_interval=30,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        logger.info(
            "Redis pool initialisé : %s (max_connections=%d)",
            self._settings.redis_url,
            self._settings.redis_max_connections,
        )

    @classmethod
    def get_client(cls, settings: Settings | None = None) -> redis.Redis:
        """
        Retourne un client Redis partagé depuis le pool.

        Usage :
            from app.redis_pool import RedisPool
            r = RedisPool.get_client()
            r.set("key", "value")
        """
        return cls.get_instance(settings)._client

    def ping(self) -> bool:
        """Vérifie la connexion Redis."""
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    def get_info(self) -> dict[str, Any]:
        """Retourne des infos sur le pool pour monitoring."""
        pool_info: dict[str, Any] = {
            "url": self._settings.redis_url,
            "max_connections": self._settings.redis_max_connections,
            "connected": self.ping(),
        }
        try:
            pool_info["created_connections"] = self._pool.created_connections()
            pool_info["available_connections"] = len(self._pool._available_connections)
            pool_info["in_use_connections"] = self._pool._in_use_connections
        except (AttributeError, TypeError):
            pool_info["created_connections"] = -1
            pool_info["available_connections"] = -1
            pool_info["in_use_connections"] = -1
        return pool_info

    def close(self) -> None:
        """Ferme toutes les connexions du pool (shutdown)."""
        self._pool.disconnect()
        logger.info("Redis pool fermé")
