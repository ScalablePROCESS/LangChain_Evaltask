"""
Circuit breaker pour OpenRouter.

Évite d'attendre le timeout (60s) quand l'API OpenRouter est indisponible.
Après N échecs consécutifs, le circuit s'ouvre et les requêtes échouent
immédiatement. Après un délai de cooldown, le circuit passe en half-open
et laisse passer une requête de test.

États :
- CLOSED : tout passe normalement
- OPEN : tout échoue immédiatement (fail-fast)
- HALF_OPEN : une requête de test passera, les autres échouent
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any

from app.observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class OpenRouterCircuitBreaker:
    """
    Circuit breaker thread-safe pour les appels OpenRouter.
    """

    _instance: OpenRouterCircuitBreaker | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, failure_threshold: int = 5, cooldown_seconds: int = 30) -> OpenRouterCircuitBreaker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(failure_threshold, cooldown_seconds)
        return cls._instance

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: int = 30):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time: float = 0
        self._lock = threading.Lock()
        self._metrics = MetricsCollector.get_instance()
        self._update_metrics()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Vérifier si le cooldown est écoulé
                if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("[circuit_breaker] OPEN → HALF_OPEN (cooldown écoulé)")
            return self._state

    def can_proceed(self) -> bool:
        """Vérifie si une requête peut être envoyée."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True  # Laisse passer une requête de test
        return False  # OPEN

    def record_success(self) -> None:
        """Enregistre un succès — réinitialise le compteur."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("[circuit_breaker] HALF_OPEN → CLOSED (succès)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
        self._update_metrics()

    def record_failure(self) -> None:
        """Enregistre un échec — peut ouvrir le circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("[circuit_breaker] HALF_OPEN → OPEN (échec test)")
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "[circuit_breaker] CLOSED → OPEN (%d échecs consécutifs)",
                    self._failure_count,
                )
        self._update_metrics()

    def reset(self) -> None:
        """Réinitialise le circuit breaker (admin)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("[circuit_breaker] Réinitialisé")
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Met à jour la jauge Prometheus du circuit breaker."""
        state = self.state
        self._metrics.set_circuit_breaker_state("openrouter", state.value)

    def get_status(self) -> dict[str, Any]:
        """Retourne le statut pour monitoring."""
        state = self.state
        return {
            "state": state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "cooldown_seconds": self._cooldown_seconds,
            "can_proceed": state != CircuitState.OPEN,
        }
