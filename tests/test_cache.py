"""Tests pour le ResponseCache."""

import json
from unittest.mock import MagicMock

from app.cache.response_cache import ResponseCache


def _make_cache(enabled=True, ttl=600):
    """Crée un ResponseCache sans Redis réel."""
    cache = ResponseCache.__new__(ResponseCache)
    cache._settings = MagicMock()
    cache._settings.cache_enabled = enabled
    cache._settings.cache_ttl_seconds = ttl
    cache._enabled = enabled
    cache._ttl = ttl
    cache._redis = MagicMock()
    cache._metrics = MagicMock()
    return cache


def test_singleton():
    """ResponseCache doit être un singleton."""
    a = ResponseCache.get_instance()
    b = ResponseCache.get_instance()
    assert a is b


def test_cache_disabled_returns_none():
    """Si le cache est désactivé, get doit retourner None."""
    cache = _make_cache(enabled=False)
    result = cache.get("t1", "hello", None, None, "model", None)
    assert result is None


def test_cache_hit():
    """get doit retourner les données si le cache hit."""
    cache = _make_cache(enabled=True)
    cached_data = {"reply": "cached response", "model_used": "gpt-4o"}
    cache._redis.get.return_value = json.dumps(cached_data)

    result = cache.get("t1", "hello", None, None, "gpt-4o", None)
    assert result is not None
    assert result["reply"] == "cached response"
    cache._metrics.record_cache_hit.assert_called_once_with("t1")


def test_cache_miss():
    """get doit retourner None et appeler record_cache_miss si pas en cache."""
    cache = _make_cache(enabled=True)
    cache._redis.get.return_value = None

    result = cache.get("t1", "hello", None, None, "gpt-4o", None)
    assert result is None
    cache._metrics.record_cache_miss.assert_called_once_with("t1")


def test_cache_set():
    """set doit stocker la réponse dans Redis avec TTL."""
    cache = _make_cache(enabled=True, ttl=600)
    cache.set(
        tenant_id="t1",
        message="hello",
        response={"reply": "world"},
        user_context=None,
        page_context=None,
        model="gpt-4o",
    )
    cache._redis.setex.assert_called_once()
    args = cache._redis.setex.call_args
    assert args.args[1] == 600  # TTL (arg 0 = key, arg 1 = ttl, arg 2 = value)
