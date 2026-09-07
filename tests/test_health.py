"""Tests pour l'endpoint healthcheck."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root():
    """Le endpoint racine doit retourner les infos du serveur."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "version" in data


@pytest.mark.asyncio
async def test_health():
    """Le endpoint health doit retourner l'état du serveur."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["server"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness():
    """Le endpoint ready doit retourner 200 ou 503 selon l'état des dépendances."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert "redis" in data["checks"]
    assert "chromadb" in data["checks"]
