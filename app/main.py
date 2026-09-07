"""
Point d'entrée principal du serveur LangChain EvalTask.

Principes appliqués :
- LLMOps Engineer : lifespan, observabilité, déploiement progressif
- LangChain Solution Architect : dégradation contrôlée
- API Designer : CORS, versioning, docs

Démarrage :
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Production :
    gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import cache, chat, costs, embed, feedback, health, keys
from app.config import get_settings
from app.observability.circuit_breaker import OpenRouterCircuitBreaker
from app.observability.logging_config import setup_logging
from app.observability.metrics import MetricsCollector
from app.redis_pool import RedisPool

# ─── Configuration du logging ───

settings = get_settings()

setup_logging(settings)
logger = logging.getLogger(__name__)


# ─── Lifespan (remplace on_event deprecated) ───


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown du serveur."""
    logger.info(
        "🚀 %s v%s démarré (port %d)",
        settings.app_name,
        settings.app_version,
        settings.port,
    )
    logger.info(
        "   OpenRouter default: %s / fallback: %s",
        settings.openrouter_default_model,
        settings.openrouter_fallback_model,
    )
    logger.info("   ChromaDB: %s", settings.chroma_persist_dir)
    logger.info("   Redis: %s", settings.redis_url)
    logger.info(
        "   Rate limit: %d req/min/tenant (embed: %d/min)",
        settings.rate_limit_requests_per_minute,
        settings.rate_limit_embed_per_minute,
    )
    logger.info("   Log format: %s", settings.log_format)
    logger.info(
        "   Circuit breaker: threshold=%d, cooldown=%ds",
        settings.circuit_breaker_failure_threshold,
        settings.circuit_breaker_cooldown_seconds,
    )

    # Initialiser le circuit breaker
    OpenRouterCircuitBreaker.get_instance(
        failure_threshold=settings.circuit_breaker_failure_threshold,
        cooldown_seconds=settings.circuit_breaker_cooldown_seconds,
    )

    yield
    logger.info("🛑 %s arrêté", settings.app_name)

    # Fermer proprement le pool Redis
    try:
        RedisPool.get_instance().close()
    except Exception:
        pass


# ─── Application FastAPI ───

app = FastAPI(
    title=settings.app_name,
    description=(
        "Serveur LangChain centralisé pour les plateformes EvalTask. "
        "Gère l'orchestration LLM (OpenRouter), le RAG multi-tenant, "
        "le tool calling et la mémoire de conversation.\n\n"
        "## Authentification\n"
        "Tous les endpoints (sauf `/` et `/api/v1/health`) requièrent un JWT "
        "signé par la plateforme cliente, passé dans l'en-tête `Authorization: Bearer <token>`.\n\n"
        "## Codes d'erreur\n"
        "- **401** — Token JWT manquant ou invalide\n"
        "- **403** — Le tenant_id du token ne correspond pas à la requête\n"
        "- **422** — Message ou tool_results manquant\n"
        "- **429** — Rate limit dépassé (voir `Retry-After`)\n"
        "- **503** — Service temporairement indisponible (circuit breaker, Redis)\n\n"
        "## Streaming SSE\n"
        "L'endpoint `/api/v1/chat/stream` émet des événements `text/event-stream`:\n"
        '- `{"type": "token", "content": "..."}` — fragment de texte\n'
        '- `{"type": "tool_calls", "tool_calls": [...]}` — outils à exécuter\n'
        '- `{"type": "done", "model_used": "...", "duration_ms": ...}` — fin du stream\n'
        '- `{"type": "error", "error": "..."}` — erreur\n'
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS ───

origins = settings.allowed_origins.split(",") if settings.allowed_origins != "*" else ["*"]
allow_credentials = origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware : corrélation et métriques ───


@app.middleware("http")
async def correlation_and_metrics(request: Request, call_next) -> Response:
    """Ajoute un request_id, mesure la durée et enregistre les métriques Prometheus."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.monotonic()

    response: Response = await call_next(request)

    duration_ms = int((time.monotonic() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Duration-Ms"] = str(duration_ms)

    if settings.metrics_enabled:
        metrics = MetricsCollector.get_instance()
        metrics.record_http_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        logger.debug(
            "[http] %s %s → %d (%dms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

    return response


# ─── Routes ───

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(embed.router)
app.include_router(keys.router)
app.include_router(costs.router)
app.include_router(cache.router)
app.include_router(feedback.router)


@app.get("/")
async def root():
    """Racine — info serveur."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/metrics")
async def metrics():
    """Endpoint Prometheus — expose les métriques au format texte."""
    from fastapi.responses import PlainTextResponse

    collector = MetricsCollector.get_instance()
    return PlainTextResponse(
        content=collector.export_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/v1/circuit-breaker")
async def circuit_breaker_status():
    """Statut du circuit breaker OpenRouter."""
    cb = OpenRouterCircuitBreaker.get_instance()
    return cb.get_status()


@app.get("/api/v1/redis/pool")
async def redis_pool_info():
    """Infos sur le pool de connexions Redis."""
    return RedisPool.get_instance().get_info()
