"""Tests pour l'authentification JWT."""

import time

import jwt
import pytest

from app.auth.jwt_auth import TenantInfo
from app.config import get_settings


def test_tenant_info_repr():
    """TenantInfo doit avoir un repr lisible."""
    info = TenantInfo(tenant_id="abc", claims={"tenant_id": "abc"})
    assert "abc" in repr(info)


def test_valid_token_decodes():
    """Un JWT valide doit être décodé correctement."""
    settings = get_settings()
    payload = {
        "tenant_id": "client_test",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert decoded["tenant_id"] == "client_test"


def test_expired_token_fails():
    """Un JWT expiré doit lever une erreur."""
    settings = get_settings()
    payload = {
        "tenant_id": "client_test",
        "iat": int(time.time()) - 600,
        "exp": int(time.time()) - 300,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def test_invalid_secret_fails():
    """Un JWT signé avec un mauvais secret doit lever une erreur."""
    settings = get_settings()
    payload = {
        "tenant_id": "client_test",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(payload, "wrong-secret", algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
