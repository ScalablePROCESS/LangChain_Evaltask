"""Tests pour le sanitize_metadata et la validation de configuration."""

import pytest
from pydantic import ValidationError

from app.auth.jwt_auth import _ALLOWED_METADATA_KEYS, sanitize_metadata


def test_sanitize_metadata_filters_unknown_keys():
    """sanitize_metadata doit filtrer les clés non autorisées."""
    metadata = {
        "source": "doc.pdf",
        "evil_key": "malicious",
        "tenant_id": "t1",
    }
    cleaned = sanitize_metadata(metadata)
    assert "source" in cleaned
    assert "tenant_id" in cleaned
    assert "evil_key" not in cleaned


def test_sanitize_metadata_truncates_long_values():
    """sanitize_metadata doit tronquer les valeurs trop longues."""
    metadata = {
        "source": "A" * 600,
    }
    cleaned = sanitize_metadata(metadata)
    assert len(cleaned["source"]) == 500


def test_sanitize_metadata_removes_none_values():
    """sanitize_metadata doit supprimer les valeurs None."""
    metadata = {
        "source": "doc.pdf",
        "category": None,
    }
    cleaned = sanitize_metadata(metadata)
    assert "source" in cleaned
    assert "category" not in cleaned


def test_sanitize_metadata_empty():
    """sanitize_metadata avec un dict vide doit retourner un dict vide."""
    assert sanitize_metadata({}) == {}
    assert sanitize_metadata(None) == {}


def test_sanitize_metadata_converts_to_string():
    """sanitize_metadata doit convertir les valeurs en string."""
    metadata = {
        "source": 12345,
        "page": 3,
    }
    cleaned = sanitize_metadata(metadata)
    assert cleaned["source"] == "12345"
    assert cleaned["page"] == "3"


def test_allowed_metadata_keys_contains_expected():
    """Les clés autorisées doivent inclure les clés attendues."""
    assert "source" in _ALLOWED_METADATA_KEYS
    assert "tenant_id" in _ALLOWED_METADATA_KEYS
    assert "filename" in _ALLOWED_METADATA_KEYS


def test_config_rejects_default_jwt_secret_in_production():
    """La config doit refuser jwt_secret par défaut si debug=False."""
    from app.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            debug=False,
            jwt_secret="change-me-in-production-not-safe",
            allowed_origins="https://example.com",
        )
    assert "JWT_SECRET" in str(exc_info.value)


def test_config_rejects_wildcard_origins_in_production():
    """La config doit refuser allowed_origins='*' si debug=False."""
    from app.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            debug=False,
            jwt_secret="a-very-secure-secret-key-with-32-bytes!",
            allowed_origins="*",
        )
    assert "ALLOWED_ORIGINS" in str(exc_info.value)


def test_config_accepts_wildcard_in_debug():
    """La config doit accepter allowed_origins='*' si debug=True."""
    from app.config import Settings

    settings = Settings(
        debug=True,
        jwt_secret="change-me-in-production-not-safe",
        allowed_origins="*",
    )
    assert settings.allowed_origins == "*"


def test_config_rejects_short_jwt_secret_in_production():
    """La config doit refuser un jwt_secret < 32 bytes en production."""
    from app.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            debug=False,
            jwt_secret="short-key",
            allowed_origins="https://example.com",
        )
    assert "JWT_SECRET" in str(exc_info.value)
    assert "32 bytes" in str(exc_info.value)
