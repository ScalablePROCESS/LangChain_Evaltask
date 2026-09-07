"""Tests pour le MetricsCollector."""

import threading

from app.observability.metrics import MetricsCollector


def test_singleton():
    """MetricsCollector doit être un singleton."""
    a = MetricsCollector.get_instance()
    b = MetricsCollector.get_instance()
    assert a is b


def test_counter_increment():
    """inc_counter doit incrémenter le compteur."""
    m = MetricsCollector()
    m.inc_counter("test_counter", {"label": "a"})
    m.inc_counter("test_counter", {"label": "a"})
    m.inc_counter("test_counter", {"label": "a"}, value=3)
    prom = m.export_prometheus()
    assert "test_counter" in prom
    assert 'label="a"' in prom


def test_gauge_set():
    """set_gauge doit définir la valeur."""
    m = MetricsCollector()
    m.set_gauge("test_gauge", 42.0, {"name": "foo"})
    prom = m.export_prometheus()
    assert "test_gauge" in prom
    assert "42" in prom


def test_histogram_observe():
    """observe_histogram doit enregistrer les valeurs."""
    m = MetricsCollector()
    m.observe_histogram("test_hist", 0.5, {"path": "/api"})
    m.observe_histogram("test_hist", 1.5, {"path": "/api"})
    prom = m.export_prometheus()
    assert "test_hist_sum" in prom
    assert "test_hist_count" in prom
    assert "test_hist_bucket" in prom
    assert 'le="0.1"' in prom


def test_record_http_request():
    """record_http_request doit enregistrer la requête."""
    m = MetricsCollector()
    m.record_http_request("GET", "/api/v1/chat", 200, 150)
    prom = m.export_prometheus()
    assert "evaltask_http_requests_total" in prom
    assert "200" in prom


def test_record_llm_call():
    """record_llm_call doit enregistrer l'appel LLM."""
    m = MetricsCollector()
    m.record_llm_call("tenant_1", "gpt-4o", "success", 500)
    prom = m.export_prometheus()
    assert "evaltask_llm_calls_total" in prom
    assert "tenant_1" in prom
    assert "gpt-4o" in prom


def test_record_cache_hit_miss():
    """record_cache_hit et record_cache_miss doivent incrémenter les compteurs."""
    m = MetricsCollector()
    m.record_cache_hit("tenant_1")
    m.record_cache_hit("tenant_1")
    m.record_cache_miss("tenant_1")
    prom = m.export_prometheus()
    assert "evaltask_cache_hits_total" in prom
    assert "evaltask_cache_misses_total" in prom


def test_thread_safety():
    """Les compteurs doivent être thread-safe."""
    m = MetricsCollector()

    def increment():
        for _ in range(100):
            m.inc_counter("thread_test", {"worker": "w1"})

    threads = [threading.Thread(target=increment) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    prom = m.export_prometheus()
    # 5 threads × 100 increments = 500
    lines = [line for line in prom.split("\n") if "thread_test" in line]
    assert any("500" in line for line in lines)
