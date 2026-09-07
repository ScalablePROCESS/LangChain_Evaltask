"""
Configuration centralisée du serveur LangChain EvalTask.

Respecte les principes :
- LangChain Solution Architect : budget par requête, latence, repli
- LLMOps Engineer : observabilité, versioning config, séparation environnements
- AI Security & Compliance : isolation secrets, rétention limitée
- LangChain Backend Engineer : timeout, retry, contrats typés
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

_INSECURE_DEFAULT_SECRET = "change-me-in-production-not-safe"


class Settings(BaseSettings):
    """Paramètres globaux du serveur LangChain EvalTask."""

    # ── Serveur ──
    app_name: str = "LangChain EvalTask Server"
    app_version: str = "2.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: str = "*"

    # ── JWT (authentification des plateformes EvalTask) ──
    jwt_secret: str = Field("change-me-in-production-not-safe", description="MUST be overridden in production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_leeway_seconds: int = 30

    # ── OpenRouter (défaut, surchargé par le tenant à chaque requête) ──
    openrouter_default_model: str = "z-ai/glm-5.2"
    openrouter_fallback_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: int = 60
    openrouter_max_retries: int = 2

    # ── Embeddings (endpoint dédié, distinct du LLM) ──
    embedding_provider_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = Field("", description="Clé dédiée pour les embeddings (optionnel, sinon clé tenant)")

    # ── Vectorstore (ChromaDB) ──
    chroma_persist_dir: str = "./data/chromadb"
    chroma_max_results: int = 5

    # ── Redis (mémoire + rate limiting) ──
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = Field(
        20,
        description="Nombre maximum de connexions dans le pool Redis.",
    )
    redis_socket_timeout: float = Field(
        5.0,
        description="Timeout socket Redis en secondes.",
    )
    conversation_ttl_seconds: int = 3600
    conversation_max_messages: int = 50

    # ── Cache de réponses LLM ──
    cache_enabled: bool = Field(
        True,
        description="Active/désactive le cache de réponses LLM dans Redis.",
    )
    cache_ttl_seconds: int = Field(
        600,
        description="TTL du cache de réponses (en secondes). Default: 10 minutes.",
    )

    # ── Limites LLM ──
    max_tool_rounds: int = 5
    max_tokens: int = 4096
    temperature: float = 0.7

    # ── Qualité conversation ──
    summary_threshold_messages: int = Field(
        10,
        description="Seuil de messages pour déclencher le résumé d'historique.",
    )
    summary_keep_recent_messages: int = Field(
        4,
        description="Nombre de messages récents conservés après le résumé.",
    )
    intent_detection_enabled: bool = Field(
        True,
        description="Active la détection d'intention pour les messages simples (salutations, etc.).",
    )

    # ── Rate limiting par tenant ──
    rate_limit_requests_per_minute: int = 30
    rate_limit_embed_per_minute: int = 10
    rate_limit_tokens_per_day: int = 500_000
    rate_limit_fail_open: bool = True

    # ── Gestion des clés API ──
    api_key_server_managed: bool = Field(
        True,
        description="Si True, les clés OpenRouter sont stockées côté serveur (chiffrées Redis). "
        "Si False, fallback sur la clé envoyée dans la requête.",
    )

    # ── Budget & coût ──
    budget_alert_threshold_usd: float = 10.0
    tenant_budget_default_usd: float = Field(
        50.0,
        description="Budget par défaut par tenant (USD). Peut être surchargé par tenant via l'API.",
    )
    cost_tracking_enabled: bool = True

    # ── Observabilité ──
    log_level: str = "INFO"
    log_format: str = Field(
        "text",
        description="Format des logs : 'text' (lisible) ou 'json' (structuré pour ELK/Datadog).",
    )
    trace_sampling_rate: float = 1.0
    metrics_enabled: bool = True

    # ── Circuit breaker ──
    circuit_breaker_failure_threshold: int = Field(
        5,
        description="Nombre d'échecs consécutifs avant d'ouvrir le circuit OpenRouter.",
    )
    circuit_breaker_cooldown_seconds: int = Field(
        30,
        description="Délai avant de tenter une requête de test (half-open).",
    )

    # ── Sécurité ──
    max_input_length: int = 10_000
    max_history_messages: int = 30
    sensitive_fields_mask: list[str] = Field(
        default=["openrouter_api_key", "jwt_secret", "embedding_api_key"],
        description="Champs masqués dans les logs et traces",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        """Valide la configuration de sécurité au démarrage."""
        if not self.debug and self.jwt_secret == _INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "JWT_SECRET doit être défini en production (debug=False). "
                "Ne laissez pas la valeur par défaut 'change-me-in-production'."
            )
        if not self.debug and len(self.jwt_secret.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET doit faire au moins 32 bytes en production (debug=False). "
                f"Actuel : {len(self.jwt_secret.encode('utf-8'))} bytes. "
                "Utilisez une clé suffisamment longue (recommandation RFC 7518)."
            )
        if not self.debug and self.allowed_origins == "*":
            raise ValueError(
                "ALLOWED_ORIGINS='*' est interdit en production (debug=False). "
                "Spécifiez une liste explicite d'origines séparées par des virgules."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton des paramètres (mis en cache)."""
    return Settings()
