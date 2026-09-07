"""
Endpoint de healthcheck pour le serveur LangChain EvalTask.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    """Vérifie l'état du serveur et de ses dépendances."""
    status = {"server": "ok", "timestamp": datetime.now(UTC).isoformat()}

    # Vérifier Redis
    try:
        from app.redis_pool import RedisPool

        r = RedisPool.get_client(settings)
        r.ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = f"error: {exc}"

    # Vérifier ChromaDB
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        client.heartbeat()
        status["chromadb"] = "ok"
    except Exception as exc:
        status["chromadb"] = f"error: {exc}"

    overall = all(v == "ok" for k, v in status.items() if k not in ("timestamp",))
    status["overall"] = "healthy" if overall else "degraded"

    return status


@router.get("/api/v1/ready")
async def readiness(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """
    Readiness probe — retourne 200 si le serveur est prêt à traiter
    des requêtes (Redis + ChromaDB disponibles), 503 sinon.
    """
    checks: dict[str, str] = {}

    # Redis
    try:
        from app.redis_pool import RedisPool

        r = RedisPool.get_client(settings)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # ChromaDB
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        client.heartbeat()
        checks["chromadb"] = "ok"
    except Exception as exc:
        checks["chromadb"] = f"error: {exc}"

    ready = all(v == "ok" for v in checks.values())
    body = {"ready": ready, "checks": checks}
    return JSONResponse(status_code=200 if ready else 503, content=body)
