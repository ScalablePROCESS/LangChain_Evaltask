"""Tests pour le circuit breaker OpenRouter."""

import pytest

from app.observability.circuit_breaker import CircuitState, OpenRouterCircuitBreaker


@pytest.fixture
def cb():
    """Circuit breaker avec threshold=3 pour les tests."""
    return OpenRouterCircuitBreaker(failure_threshold=3, cooldown_seconds=1)


def test_initial_state_is_closed(cb):
    """Le circuit breaker doit démarrer à CLOSED."""
    assert cb.state == CircuitState.CLOSED
    assert cb.can_proceed() is True


def test_opens_after_threshold(cb):
    """Le circuit doit s'ouvrir après N échecs consécutifs."""
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_proceed() is False


def test_success_resets_counter(cb):
    """Un succès doit réinitialiser le compteur d'échecs."""
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    # Le compteur est réinitialisé, il faut 3 échecs pour ouvrir
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_half_open_after_cooldown(cb):
    """Le circuit doit passer à HALF_OPEN après le cooldown."""
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    import time

    time.sleep(1.1)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.can_proceed() is True


def test_half_open_success_closes(cb):
    """Un succès en HALF_OPEN doit fermer le circuit."""
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    import time

    time.sleep(1.1)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens(cb):
    """Un échec en HALF_OPEN doit rouvrir le circuit."""
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    import time

    time.sleep(1.1)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_reset(cb):
    """reset() doit remettre le circuit à CLOSED."""
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_get_status(cb):
    """get_status() doit retourner un dict avec les bonnes clés."""
    status = cb.get_status()
    assert "state" in status
    assert "failure_count" in status
    assert "failure_threshold" in status
    assert "cooldown_seconds" in status
    assert "can_proceed" in status
    assert status["state"] == "closed"
    assert status["can_proceed"] is True
