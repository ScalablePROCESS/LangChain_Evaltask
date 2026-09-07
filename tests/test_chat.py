"""Tests pour l'endpoint chat."""

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


def _make_token(tenant_id: str = "test_tenant") -> str:
    """Génère un JWT de test."""
    settings = get_settings()
    import time

    payload = {
        "tenant_id": tenant_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.mark.asyncio
async def test_chat_requires_auth():
    """L'endpoint chat doit exiger un JWT valide."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "Bonjour",
                "tenant_id": "test",
                "openrouter_api_key": "fake",
            },
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_chat_rejects_empty_message():
    """L'endpoint chat doit rejeter un message vide."""
    token = _make_token("test_tenant")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "tenant_id": "test_tenant",
                "openrouter_api_key": "fake",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_tenant_mismatch():
    """L'endpoint chat doit rejeter un tenant_id qui ne correspond pas au JWT."""
    token = _make_token("tenant_A")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "Bonjour",
                "tenant_id": "tenant_B",
                "openrouter_api_key": "fake",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
