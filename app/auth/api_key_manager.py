"""
Gestionnaire de clés API OpenRouter par tenant.

Stocke les clés de manière chiffrée dans Redis, isolées par tenant.
Évite la transmission de la clé en clair dans chaque requête HTTP.

Principes :
- AI Security & Compliance : chiffrement au repos, isolation par tenant, audit
- LangChain Backend Engineer : cache en mémoire, fallback élégant
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading

from cryptography.fernet import Fernet

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)

# TTL par défaut pour le cache en mémoire (5 minutes)
_CACHE_TTL_SECONDS = 300


class APIKeyManager:
    """
    Gère les clés API OpenRouter par tenant de manière sécurisée.

    - Stockage chiffré dans Redis (clé dérivée du JWT_SECRET)
    - Cache en mémoire avec TTL pour éviter les round-trips Redis
    - Fallback : si aucune clé n'est stockée pour un tenant, utilise la clé
      fournie dans la requête (rétrocompatibilité)
    """

    _instance: APIKeyManager | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> APIKeyManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = RedisPool.get_client(settings)
        self._cipher = self._create_cipher()
        self._cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = _CACHE_TTL_SECONDS

    def _create_cipher(self) -> Fernet:
        """Dérive une clé de chiffrement Fernet à partir du JWT_SECRET."""
        # Dériver une clé 32 bytes via SHA-256, puis encoder en base64 url-safe
        key_material = hashlib.sha256(self._settings.jwt_secret.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_material)
        return Fernet(fernet_key)

    def _redis_key(self, tenant_id: str) -> str:
        return f"evaltask:apikey:{tenant_id}"

    def store_key(self, tenant_id: str, api_key: str) -> None:
        """Stocke (ou met à jour) la clé API chiffrée pour un tenant."""
        encrypted = self._cipher.encrypt(api_key.encode("utf-8")).decode("utf-8")
        self._redis.set(self._redis_key(tenant_id), encrypted)
        # Invalider le cache
        self._cache.pop(tenant_id, None)
        logger.info("[apikey] Clé stockée pour tenant %s", tenant_id)

    def get_key(self, tenant_id: str, fallback: str | None = None) -> str | None:
        """
        Récupère la clé API d'un tenant.

        Priorité :
        1. Cache en mémoire (si non expiré)
        2. Redis (chiffré)
        3. Fallback (clé fournie dans la requête, pour rétrocompatibilité)

        Retourne None si aucune clé n'est trouvée.
        """
        import time

        # 1. Cache en mémoire
        cached = self._cache.get(tenant_id)
        if cached:
            key, expires_at = cached
            if time.time() < expires_at:
                return key
            self._cache.pop(tenant_id, None)

        # 2. Redis
        try:
            encrypted = self._redis.get(self._redis_key(tenant_id))
            if encrypted:
                decrypted = self._cipher.decrypt(encrypted.encode("utf-8")).decode("utf-8")
                self._cache[tenant_id] = (decrypted, time.time() + self._cache_ttl)
                return decrypted
        except Exception as exc:
            logger.warning("[apikey] Erreur récupération Redis pour %s: %s", tenant_id, exc)

        # 3. Fallback
        if fallback:
            logger.debug("[apikey] Utilisation fallback pour tenant %s", tenant_id)
            return fallback

        return None

    def delete_key(self, tenant_id: str) -> bool:
        """Supprime la clé API d'un tenant."""
        self._cache.pop(tenant_id, None)
        deleted = self._redis.delete(self._redis_key(tenant_id))
        logger.info("[apikey] Clé supprimée pour tenant %s", tenant_id)
        return bool(deleted)

    def has_key(self, tenant_id: str) -> bool:
        """Vérifie si une clé est stockée pour un tenant."""
        import time

        cached = self._cache.get(tenant_id)
        if cached and time.time() < cached[1]:
            return True

        try:
            return bool(self._redis.exists(self._redis_key(tenant_id)))
        except Exception:
            return False
