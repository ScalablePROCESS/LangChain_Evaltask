"""
Suivi des coûts LLM par tenant via Redis.

Stocke les tokens consommés (prompt + completion) et calcule le coût estimé
basé sur les tarifs des modèles OpenRouter.

Principes :
- LLMOps Engineer : observabilité coût, alertes budget
- AI Security & Compliance : isolation par tenant, pas de données sensibles
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.redis_pool import RedisPool

logger = logging.getLogger(__name__)

# Tarifs approximatifs par modèle (USD pour 1M tokens)
# Source : OpenRouter pricing (mis à jour périodiquement)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "z-ai/glm-5.2": {"prompt": 0.50, "completion": 1.50},
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "openai/gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "anthropic/claude-3.5-sonnet": {"prompt": 3.00, "completion": 15.00},
    "google/gemini-2.0-flash": {"prompt": 0.10, "completion": 0.40},
}

# Tarif par défaut si modèle inconnu
DEFAULT_PRICING = {"prompt": 1.00, "completion": 3.00}


class CostTracker:
    """
    Tracking des coûts LLM par tenant dans Redis.

    Structure Redis :
    - evaltask:cost:{tenant_id}:current  → hash avec total_tokens, total_cost_usd, etc.
    - evaltask:cost:{tenant_id}:daily:{YYYY-MM-DD}  → hash par jour
    - evaltask:cost:{tenant_id}:log  → list (derniers 100 appels)
    """

    _instance: CostTracker | None = None

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> CostTracker:
        if cls._instance is None:
            cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = RedisPool.get_client(settings)

    def _get_pricing(self, model: str) -> dict[str, float]:
        """Retourne le tarif d'un modèle (prompt/completion pour 1M tokens)."""
        return MODEL_PRICING.get(model, DEFAULT_PRICING)

    def _compute_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calcule le coût USD pour un appel."""
        pricing = self._get_pricing(model)
        cost = (prompt_tokens / 1_000_000) * pricing["prompt"] + (completion_tokens / 1_000_000) * pricing["completion"]
        return round(cost, 6)

    def record_usage(
        self,
        tenant_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Enregistre la consommation d'un appel LLM.

        Returns:
            Dict avec cost_usd, prompt_tokens, completion_tokens, total_tokens
        """
        if not self._settings.cost_tracking_enabled:
            return {"cost_usd": 0.0, "tracked": False}

        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self._compute_cost(model, prompt_tokens, completion_tokens)
        today = time.strftime("%Y-%m-%d")

        pipe = self._redis.pipeline()

        # Compteurs globaux du tenant
        current_key = f"evaltask:cost:{tenant_id}:current"
        pipe.hincrby(current_key, "prompt_tokens", prompt_tokens)
        pipe.hincrby(current_key, "completion_tokens", completion_tokens)
        pipe.hincrby(current_key, "total_tokens", total_tokens)
        pipe.hincrbyfloat(current_key, "total_cost_usd", cost_usd)
        pipe.hincrby(current_key, "request_count", 1)

        # Compteurs quotidiens
        daily_key = f"evaltask:cost:{tenant_id}:daily:{today}"
        pipe.hincrby(daily_key, "prompt_tokens", prompt_tokens)
        pipe.hincrby(daily_key, "completion_tokens", completion_tokens)
        pipe.hincrby(daily_key, "total_tokens", total_tokens)
        pipe.hincrbyfloat(daily_key, "total_cost_usd", cost_usd)
        pipe.hincrby(daily_key, "request_count", 1)
        pipe.expire(daily_key, 90 * 24 * 3600)  # 90 jours de rétention

        # Log des derniers appels (liste circulaire)
        log_key = f"evaltask:cost:{tenant_id}:log"
        log_entry = json.dumps(
            {
                "request_id": request_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "timestamp": time.time(),
            }
        )
        pipe.lpush(log_key, log_entry)
        pipe.ltrim(log_key, 0, 99)  # Garder les 100 derniers
        pipe.expire(log_key, 7 * 24 * 3600)  # 7 jours

        pipe.execute()

        logger.info(
            "[%s] Coût LLM: %s prompt=%d completion=%d total=%d cost=$%.6f",
            tenant_id,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_usd,
        )

        return {
            "cost_usd": cost_usd,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tracked": True,
        }

    def get_summary(self, tenant_id: str) -> dict[str, Any]:
        """
        Retourne le résumé des coûts pour un tenant.
        """
        current_key = f"evaltask:cost:{tenant_id}:current"
        data = self._redis.hgetall(current_key)

        if not data:
            return {
                "tenant_id": tenant_id,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "request_count": 0,
                "budget_threshold_usd": self.get_tenant_budget(tenant_id),
                "budget_exceeded": False,
            }

        total_cost = float(data.get("total_cost_usd", 0))
        budget = self.get_tenant_budget(tenant_id)

        return {
            "tenant_id": tenant_id,
            "prompt_tokens": int(data.get("prompt_tokens", 0)),
            "completion_tokens": int(data.get("completion_tokens", 0)),
            "total_tokens": int(data.get("total_tokens", 0)),
            "total_cost_usd": round(total_cost, 6),
            "request_count": int(data.get("request_count", 0)),
            "budget_threshold_usd": budget,
            "budget_exceeded": total_cost >= budget,
        }

    def get_daily_breakdown(self, tenant_id: str, days: int = 7) -> list[dict[str, Any]]:
        """
        Retourne la consommation jour par jour pour les N derniers jours.
        """
        results = []
        for i in range(days):
            day = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            daily_key = f"evaltask:cost:{tenant_id}:daily:{day}"
            data = self._redis.hgetall(daily_key)

            if data:
                results.append(
                    {
                        "date": day,
                        "prompt_tokens": int(data.get("prompt_tokens", 0)),
                        "completion_tokens": int(data.get("completion_tokens", 0)),
                        "total_tokens": int(data.get("total_tokens", 0)),
                        "total_cost_usd": round(float(data.get("total_cost_usd", 0)), 6),
                        "request_count": int(data.get("request_count", 0)),
                    }
                )
            else:
                results.append(
                    {
                        "date": day,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "total_cost_usd": 0.0,
                        "request_count": 0,
                    }
                )

        return results

    def get_recent_logs(self, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Retourne les derniers appels LLM logged pour un tenant.
        """
        log_key = f"evaltask:cost:{tenant_id}:log"
        raw_entries = self._redis.lrange(log_key, 0, limit - 1)

        logs = []
        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                logs.append(entry)
            except json.JSONDecodeError:
                continue

        return logs

    def check_budget(self, tenant_id: str) -> dict[str, Any]:
        """
        Vérifie si le tenant a dépassé son budget.
        """
        summary = self.get_summary(tenant_id)
        budget = self.get_tenant_budget(tenant_id)
        exceeded = summary["total_cost_usd"] >= budget

        if exceeded:
            logger.warning(
                "[%s] Budget dépassé : $%.4f / $%.4f",
                tenant_id,
                summary["total_cost_usd"],
                budget,
            )

        return {
            "tenant_id": tenant_id,
            "total_cost_usd": summary["total_cost_usd"],
            "budget_threshold_usd": budget,
            "exceeded": exceeded,
            "remaining_usd": round(max(0, budget - summary["total_cost_usd"]), 6),
        }

    def get_tenant_budget(self, tenant_id: str) -> float:
        """Retourne le budget d'un tenant (surcharge Redis ou valeur par défaut)."""
        key = f"evaltask:cost:{tenant_id}:budget"
        value = self._redis.get(key)
        if value is not None:
            return float(value)
        return self._settings.tenant_budget_default_usd

    def set_tenant_budget(self, tenant_id: str, budget_usd: float) -> None:
        """Définit le budget personnalisé d'un tenant."""
        key = f"evaltask:cost:{tenant_id}:budget"
        self._redis.set(key, str(budget_usd))
        logger.info("[%s] Budget défini à $%.2f", tenant_id, budget_usd)

    def reset_tenant(self, tenant_id: str) -> None:
        """Réinitialise les compteurs de coût d'un tenant."""
        # Supprimer les clés de coût
        self._redis.delete(f"evaltask:cost:{tenant_id}:current")
        self._redis.delete(f"evaltask:cost:{tenant_id}:log")

        # Supprimer les clés quotidiennes
        for key in self._redis.scan_iter(f"evaltask:cost:{tenant_id}:daily:*"):
            self._redis.delete(key)

        logger.info("[%s] Compteurs de coût réinitialisés", tenant_id)
