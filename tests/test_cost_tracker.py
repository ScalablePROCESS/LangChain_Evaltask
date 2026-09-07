"""Tests pour le CostTracker."""

from unittest.mock import MagicMock

from app.cost.tracker import DEFAULT_PRICING, MODEL_PRICING, CostTracker


def test_get_pricing_known_model():
    """_get_pricing doit retourner le tarif d'un modèle connu."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.cost_tracking_enabled = True
    tracker._redis = MagicMock()
    pricing = tracker._get_pricing("openai/gpt-4o")
    assert pricing == MODEL_PRICING["openai/gpt-4o"]


def test_get_pricing_unknown_model():
    """_get_pricing doit retourner le tarif par défaut pour un modèle inconnu."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.cost_tracking_enabled = True
    tracker._redis = MagicMock()
    pricing = tracker._get_pricing("unknown/model")
    assert pricing == DEFAULT_PRICING


def test_compute_cost():
    """_compute_cost doit calculer le coût correctement."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.cost_tracking_enabled = True
    tracker._redis = MagicMock()
    # gpt-4o: prompt=2.50, completion=10.00 per 1M tokens
    cost = tracker._compute_cost("openai/gpt-4o", 1000, 500)
    expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
    assert abs(cost - round(expected, 6)) < 0.000001


def test_compute_cost_unknown_model():
    """_compute_cost doit utiliser le tarif par défaut pour un modèle inconnu."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.cost_tracking_enabled = True
    tracker._redis = MagicMock()
    cost = tracker._compute_cost("unknown/model", 1000, 500)
    expected = (1000 / 1_000_000) * 1.00 + (500 / 1_000_000) * 3.00
    assert abs(cost - round(expected, 6)) < 0.000001


def test_record_usage_disabled():
    """record_usage doit retourner tracked=False si le tracking est désactivé."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.cost_tracking_enabled = False
    tracker._redis = MagicMock()
    result = tracker.record_usage("t1", "model", 100, 50)
    assert result["tracked"] is False
    assert result["cost_usd"] == 0.0


def test_get_tenant_budget_default():
    """get_tenant_budget doit retourner le budget par défaut si non défini."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.tenant_budget_default_usd = 50.0
    tracker._redis = MagicMock()
    tracker._redis.get.return_value = None
    budget = tracker.get_tenant_budget("t1")
    assert budget == 50.0


def test_get_tenant_budget_custom():
    """get_tenant_budget doit retourner le budget personnalisé si défini."""
    tracker = CostTracker.__new__(CostTracker)
    tracker._settings = MagicMock()
    tracker._settings.tenant_budget_default_usd = 50.0
    tracker._redis = MagicMock()
    tracker._redis.get.return_value = "100.0"
    budget = tracker.get_tenant_budget("t1")
    assert budget == 100.0
