"""Tests pour le FeedbackStore."""

from unittest.mock import MagicMock

import pytest

from app.feedback.store import FeedbackStore


def test_singleton():
    """FeedbackStore doit être un singleton."""
    a = FeedbackStore.get_instance()
    b = FeedbackStore.get_instance()
    assert a is b


def test_record_feedback_up():
    """record_feedback avec rating='up' doit incrémenter thumbs_up."""
    store = FeedbackStore.__new__(FeedbackStore)
    store._settings = MagicMock()
    store._redis = MagicMock()
    store._redis.pipeline.return_value.__enter__ = MagicMock(return_value=store._redis)
    store._redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)

    result = store.record_feedback(
        tenant_id="t1",
        request_id="req-1",
        rating="up",
        comment="Great!",
    )
    assert result["status"] == "ok"
    assert result["rating"] == "up"


def test_record_feedback_invalid_rating():
    """record_feedback doit rejeter un rating invalide."""
    store = FeedbackStore.__new__(FeedbackStore)
    store._settings = MagicMock()
    store._redis = MagicMock()

    with pytest.raises(ValueError):
        store.record_feedback(
            tenant_id="t1",
            request_id="req-1",
            rating="sideways",
        )


def test_get_stats_empty():
    """get_stats doit retourner des stats à 0 si pas de données."""
    store = FeedbackStore.__new__(FeedbackStore)
    store._settings = MagicMock()
    store._redis = MagicMock()
    store._redis.hgetall.return_value = {}

    stats = store.get_stats("t1")
    assert stats["total"] == 0
    assert stats["thumbs_up"] == 0
    assert stats["thumbs_down"] == 0
    assert stats["satisfaction_rate_pct"] == 0.0


def test_get_stats_with_data():
    """get_stats doit retourner les bonnes stats."""
    store = FeedbackStore.__new__(FeedbackStore)
    store._settings = MagicMock()
    store._redis = MagicMock()
    store._redis.hgetall.return_value = {
        "thumbs_up": "38",
        "thumbs_down": "7",
        "total": "45",
    }

    stats = store.get_stats("t1")
    assert stats["thumbs_up"] == 38
    assert stats["thumbs_down"] == 7
    assert stats["total"] == 45
    assert stats["satisfaction_rate_pct"] == pytest.approx(84.44, abs=0.1)
