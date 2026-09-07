"""
Collecteur de métriques au format Prometheus.

Expose des compteurs et jauges pour le monitoring :
- Requêtes HTTP (total, par status, par endpoint)
- Appels LLM (total, par modèle, par tenant, durée)
- Coûts LLM (total USD, par tenant)
- Cache hits/misses
- Circuit breaker state

Format texte Prometheus (pas de dépendance externe).
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collecteur de métriques thread-safe au format Prometheus.

    Métriques exposées :
    - evaltask_http_requests_total{method, path, status}
    - evaltask_http_request_duration_seconds{method, path}
    - evaltask_llm_calls_total{tenant_id, model, status}
    - evaltask_llm_duration_seconds{tenant_id, model}
    - evaltask_llm_cost_usd_total{tenant_id}
    - evaltask_cache_hits_total{tenant_id}
    - evaltask_cache_misses_total{tenant_id}
    - evaltask_circuit_breaker_state{provider}
    - evaltask_active_conversations
    """

    _instance: MetricsCollector | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> MetricsCollector:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )
        self._gauges: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    # ─── Prometheus standard buckets (seconds) ───
    _DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    # ─── Counters ───

    def inc_counter(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._counters[name][key] += value

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._gauges[f"{name}:{key}"] = value

    # ─── Histograms (Prometheus-style cumulative buckets) ───

    def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            hist = self._histograms[name][key]
            hist["_sum"] += value
            hist["_count"] += 1
            for bucket in self._DEFAULT_BUCKETS:
                if value <= bucket:
                    hist[f"le={bucket}"] += 1
            # +Inf bucket = total count
            hist["le=+Inf"] = hist["_count"]

    # ─── Helpers ───

    def _labels_key(self, labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _format_labels(self, labels: dict[str, str]) -> str:
        if not labels:
            return ""
        pairs = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return "{" + pairs + "}"

    def _parse_labels_key(self, key: str) -> dict[str, str]:
        if not key:
            return {}
        labels = {}
        for pair in key.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                labels[k] = v
        return labels

    # ─── Convenience methods ───

    def record_http_request(self, method: str, path: str, status: int, duration_ms: float) -> None:
        self.inc_counter("evaltask_http_requests_total", {"method": method, "path": path, "status": str(status)})
        self.observe_histogram(
            "evaltask_http_request_duration_seconds", duration_ms / 1000.0, {"method": method, "path": path}
        )

    def record_llm_call(self, tenant_id: str, model: str, status: str, duration_ms: float) -> None:
        self.inc_counter("evaltask_llm_calls_total", {"tenant_id": tenant_id, "model": model, "status": status})
        self.observe_histogram(
            "evaltask_llm_duration_seconds", duration_ms / 1000.0, {"tenant_id": tenant_id, "model": model}
        )

    def record_llm_cost(self, tenant_id: str, cost_usd: float) -> None:
        self.inc_counter("evaltask_llm_cost_usd_total", {"tenant_id": tenant_id}, cost_usd)

    def record_cache_hit(self, tenant_id: str) -> None:
        self.inc_counter("evaltask_cache_hits_total", {"tenant_id": tenant_id})

    def record_cache_miss(self, tenant_id: str) -> None:
        self.inc_counter("evaltask_cache_misses_total", {"tenant_id": tenant_id})

    def set_circuit_breaker_state(self, provider: str, state: str) -> None:
        self.set_gauge("evaltask_circuit_breaker_state", 1.0, {"provider": provider, "state": state})

    def set_active_conversations(self, count: int) -> None:
        self.set_gauge("evaltask_active_conversations", float(count))

    # ─── Export Prometheus ───

    def export_prometheus(self) -> str:
        """Génère le texte au format Prometheus exposition."""
        lines = []

        with self._lock:
            # Counters
            for name, label_dict in self._counters.items():
                for label_key, value in label_dict.items():
                    labels = self._parse_labels_key(label_key)
                    lines.append(f"{name}{self._format_labels(labels)} {value}")

            # Gauges
            for gauge_key, value in self._gauges.items():
                name, _, label_key = gauge_key.partition(":")
                labels = self._parse_labels_key(label_key)
                lines.append(f"{name}{self._format_labels(labels)} {value}")

            # Histograms (Prometheus bucket format)
            for name, label_dict in self._histograms.items():
                for label_key, hist in label_dict.items():
                    labels = self._parse_labels_key(label_key)
                    # Cumulative buckets
                    for bucket in self._DEFAULT_BUCKETS:
                        bucket_labels = {**labels, "le": str(bucket)}
                        lines.append(f"{name}_bucket{self._format_labels(bucket_labels)} {hist.get(f'le={bucket}', 0)}")
                    # +Inf bucket
                    inf_labels = {**labels, "le": "+Inf"}
                    lines.append(f"{name}_bucket{self._format_labels(inf_labels)} {hist.get('le=+Inf', 0)}")
                    # Sum and count
                    lines.append(f"{name}_sum{self._format_labels(labels)} {hist.get('_sum', 0)}")
                    lines.append(f"{name}_count{self._format_labels(labels)} {hist.get('_count', 0)}")

        return "\n".join(lines) + "\n"
