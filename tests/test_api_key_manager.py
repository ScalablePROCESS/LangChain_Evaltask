"""Tests pour l'APIKeyManager (chiffrement Fernet)."""

from unittest.mock import MagicMock

from cryptography.fernet import Fernet

from app.auth.api_key_manager import APIKeyManager


def _make_manager():
    """Crée un APIKeyManager avec un Redis mocké."""
    manager = APIKeyManager.__new__(APIKeyManager)
    manager._settings = MagicMock()
    manager._settings.jwt_secret = "test-secret-key-for-fernet-encryption"
    manager._redis = MagicMock()
    manager._cache = {}
    manager._cache_ttl = 300
    # Créer un vrai cipher Fernet
    import base64
    import hashlib

    key_material = hashlib.sha256(manager._settings.jwt_secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_material)
    manager._cipher = Fernet(fernet_key)
    return manager


def test_store_key_encrypts():
    """store_key doit chiffrer la clé avant de la stocker dans Redis."""
    manager = _make_manager()
    manager.store_key("tenant_1", "sk-or-v1-abc123")

    manager._redis.set.assert_called_once()
    stored_key, stored_value = manager._redis.set.call_args.args
    assert "tenant_1" in stored_key
    # La valeur stockée ne doit pas contenir la clé en clair
    assert "sk-or-v1-abc123" not in stored_value


def test_get_key_from_redis():
    """get_key doit déchiffrer et retourner la clé depuis Redis."""
    manager = _make_manager()
    # Stocker une clé chiffrée
    encrypted = manager._cipher.encrypt(b"sk-or-v1-secret").decode("utf-8")
    manager._redis.get.return_value = encrypted

    result = manager.get_key("tenant_1")
    assert result == "sk-or-v1-secret"


def test_get_key_from_cache():
    """get_key doit utiliser le cache en mémoire si disponible."""
    import time

    manager = _make_manager()
    manager._cache["tenant_1"] = ("sk-or-v1-cached", time.time() + 300)

    result = manager.get_key("tenant_1")
    assert result == "sk-or-v1-cached"
    # Redis ne doit pas être appelé
    manager._redis.get.assert_not_called()


def test_get_key_expired_cache_falls_back_to_redis():
    """get_key doit ignorer le cache expiré et aller chercher dans Redis."""
    import time

    manager = _make_manager()
    manager._cache["tenant_1"] = ("sk-or-v1-old", time.time() - 100)
    encrypted = manager._cipher.encrypt(b"sk-or-v1-from-redis").decode("utf-8")
    manager._redis.get.return_value = encrypted

    result = manager.get_key("tenant_1")
    assert result == "sk-or-v1-from-redis"


def test_get_key_fallback():
    """get_key doit utiliser le fallback si Redis est vide."""
    manager = _make_manager()
    manager._redis.get.return_value = None

    result = manager.get_key("tenant_1", fallback="sk-or-v1-fallback")
    assert result == "sk-or-v1-fallback"


def test_get_key_no_fallback_returns_none():
    """get_key doit retourner None si ni Redis ni fallback n'ont de clé."""
    manager = _make_manager()
    manager._redis.get.return_value = None

    result = manager.get_key("tenant_1")
    assert result is None


def test_delete_key():
    """delete_key doit supprimer la clé de Redis et du cache."""
    manager = _make_manager()
    manager._cache["tenant_1"] = ("key", 9999999999.0)
    manager._redis.delete.return_value = 1

    result = manager.delete_key("tenant_1")
    assert result is True
    assert "tenant_1" not in manager._cache
    manager._redis.delete.assert_called_once()


def test_has_key_true():
    """has_key doit retourner True si la clé existe dans Redis."""
    manager = _make_manager()
    manager._redis.exists.return_value = 1

    assert manager.has_key("tenant_1") is True


def test_has_key_false():
    """has_key doit retourner False si la clé n'existe pas."""
    manager = _make_manager()
    manager._redis.exists.return_value = 0

    assert manager.has_key("tenant_1") is False


def test_has_key_from_cache():
    """has_key doit retourner True si la clé est en cache non expiré."""
    import time

    manager = _make_manager()
    manager._cache["tenant_1"] = ("key", time.time() + 300)

    assert manager.has_key("tenant_1") is True
    manager._redis.exists.assert_not_called()


def test_store_key_invalidates_cache():
    """store_key doit invalider le cache pour le tenant."""
    import time

    manager = _make_manager()
    manager._cache["tenant_1"] = ("old-key", time.time() + 300)

    manager.store_key("tenant_1", "new-key")
    assert "tenant_1" not in manager._cache


def test_encrypt_decrypt_roundtrip():
    """Le chiffrement puis déchiffrement doit préserver la clé originale."""
    manager = _make_manager()
    original = "sk-or-v1-my-secret-api-key-12345"

    # Chiffrer
    encrypted = manager._cipher.encrypt(original.encode("utf-8"))
    assert encrypted.decode("utf-8") != original

    # Déchiffrer
    decrypted = manager._cipher.decrypt(encrypted).decode("utf-8")
    assert decrypted == original
