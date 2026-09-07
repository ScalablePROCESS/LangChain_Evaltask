"""Tests pour le ConversationSummarizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.conversation.summarizer import ConversationSummarizer


def _make_summarizer(threshold=5, keep_recent=2):
    """Crée un ConversationSummarizer avec un Redis mocké."""
    s = ConversationSummarizer.__new__(ConversationSummarizer)
    s._settings = MagicMock()
    s._settings.summary_threshold_messages = threshold
    s._settings.summary_keep_recent_messages = keep_recent
    s._settings.conversation_ttl_seconds = 3600
    s._redis = MagicMock()
    s._summary_threshold = threshold
    s._keep_recent = keep_recent
    return s


def test_singleton():
    """ConversationSummarizer doit être un singleton."""
    a = ConversationSummarizer.get_instance()
    b = ConversationSummarizer.get_instance()
    assert a is b


def test_needs_summary_false_short():
    """needs_summary doit retourner False si l'historique est court."""
    s = _make_summarizer(threshold=5)
    assert s.needs_summary([]) is False
    assert s.needs_summary([{"role": "user", "content": "hi"}]) is False
    assert s.needs_summary([{"role": "user", "content": f"msg {i}"} for i in range(4)]) is False


def test_needs_summary_true_long():
    """needs_summary doit retourner True si l'historique dépasse le seuil."""
    s = _make_summarizer(threshold=5)
    history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
    assert s.needs_summary(history) is True


def test_needs_summary_none():
    """needs_summary doit retourner False pour None."""
    s = _make_summarizer()
    assert s.needs_summary(None) is False


def test_compute_history_hash_consistent():
    """_compute_history_hash doit être déterministe."""
    s = _make_summarizer()
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    h1 = s._compute_history_hash(history)
    h2 = s._compute_history_hash(history)
    assert h1 == h2
    assert len(h1) == 16  # Tronqué à 16 chars


def test_compute_history_hash_different_for_different_history():
    """_compute_history_hash doit changer si l'historique change."""
    s = _make_summarizer()
    h1 = s._compute_history_hash([{"role": "user", "content": "hello"}])
    h2 = s._compute_history_hash([{"role": "user", "content": "bye"}])
    assert h1 != h2


def test_format_history_for_summary():
    """_format_history_for_summary doit formater correctement."""
    s = _make_summarizer()
    history = [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Salut"},
        {"role": "tool_results", "content": [{"tool_name": "get_project", "result": "PRJ-001"}]},
    ]
    text = s._format_history_for_summary(history)
    assert "Utilisateur: Bonjour" in text
    assert "Assistant: Salut" in text
    assert "get_project" in text
    assert "PRJ-001" in text


def test_format_history_with_string_tool_results():
    """_format_history_for_summary doit gérer les tool_results en string."""
    s = _make_summarizer()
    history = [
        {"role": "tool_results", "content": "raw string result"},
    ]
    text = s._format_history_for_summary(history)
    assert "Outil: raw string result" in text


@pytest.mark.asyncio
async def test_get_or_create_summary_from_cache():
    """get_or_create_summary doit réutiliser le cache si le hash correspond."""
    s = _make_summarizer(threshold=3, keep_recent=2)
    history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
    history_hash = s._compute_history_hash(history)

    s._redis.hgetall.return_value = {
        "hash": history_hash,
        "summary": "Résumé de test",
    }

    llm = AsyncMock()
    summary, recent = await s.get_or_create_summary(history, "t1", "s1", llm)

    assert summary == "Résumé de test"
    assert len(recent) == 2  # keep_recent=2
    # Le LLM ne doit pas être appelé
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_summary_generates_new():
    """get_or_create_summary doit générer un résumé via LLM si pas en cache."""
    s = _make_summarizer(threshold=3, keep_recent=2)
    history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]

    s._redis.hgetall.return_value = {}

    mock_response = MagicMock()
    mock_response.content = "Ceci est un résumé généré."
    llm = AsyncMock()
    llm.ainvoke.return_value = mock_response

    summary, recent = await s.get_or_create_summary(history, "t1", "s1", llm)

    assert summary == "Ceci est un résumé généré."
    assert len(recent) == 2
    llm.ainvoke.assert_called_once()
    # Le résumé doit être mis en cache
    s._redis.hset.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_summary_llm_failure_fallback():
    """get_or_create_summary doit fallback sur historique tronqué si LLM échoue."""
    s = _make_summarizer(threshold=3, keep_recent=2)
    history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]

    s._redis.hgetall.return_value = {}

    llm = AsyncMock()
    llm.ainvoke.side_effect = Exception("LLM error")

    summary, recent = await s.get_or_create_summary(history, "t1", "s1", llm)

    assert summary == ""
    assert len(recent) == 2


@pytest.mark.asyncio
async def test_get_or_create_summary_no_summary_needed():
    """get_or_create_summary doit retourner ('', history) si pas besoin de résumé."""
    s = _make_summarizer(threshold=10, keep_recent=2)
    history = [{"role": "user", "content": "hello"}]

    llm = AsyncMock()
    summary, recent = await s.get_or_create_summary(history, "t1", "s1", llm)

    assert summary == ""
    assert recent == history
    llm.ainvoke.assert_not_called()


def test_invalidate():
    """invalidate doit supprimer le résumé du cache Redis."""
    s = _make_summarizer()
    s.invalidate("t1", "s1")
    s._redis.delete.assert_called_once_with("evaltask:summary:t1:s1")
