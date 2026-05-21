"""
core/metrics.py -- Prometheus metrics registry for autocode & gateway telemetry.

Tracks:
  - Node execution duration (histogram)
  - Terminal task status counts (counter)
  - TDD iterations per task (histogram)
  - LLM token consumption (counter)

Gracefully degrades if prometheus_client is not installed. All helpers are
safe to call anywhere; they become no-ops when the library is missing.

Usage:
    from core.metrics import track_node, track_task_status, generate_metrics

    track_node("node_run_tests", duration=2.4)
    track_task_status("success")
    print(generate_metrics())  # Prometheus text format
"""
from __future__ import annotations

try:
    from prometheus_client import (
        CollectorRegistry, Histogram, Counter,
        generate_latest, CONTENT_TYPE_LATEST
    )
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False

registry = CollectorRegistry() if _PROM_AVAILABLE else None

if _PROM_AVAILABLE:
    NODE_DURATION = Histogram(
        "autocode_node_duration_seconds",
        "Duration of autocode node execution",
        ["node_name"],
        registry=registry
    )
    TASK_STATUS = Counter(
        "autocode_task_status_total",
        "Total autocode tasks by terminal status",
        ["status"],
        registry=registry
    )
    TDD_ITERATIONS = Histogram(
        "autocode_tdd_iterations",
        "TDD iterations per task",
        registry=registry
    )
    LLM_TOKENS = Counter(
        "autocode_llm_tokens_total",
        "Total LLM tokens consumed",
        ["role"],
        registry=registry
    )

def track_node(node_name: str, duration: float) -> None:
    if _PROM_AVAILABLE:
        NODE_DURATION.labels(node_name=node_name).observe(duration)

def track_task_status(status: str) -> None:
    if _PROM_AVAILABLE:
        TASK_STATUS.labels(status=status).inc()

def track_tdd_iterations(count: int) -> None:
    if _PROM_AVAILABLE:
        TDD_ITERATIONS.observe(count)

def track_llm_tokens(role: str, prompt: int, completion: int) -> None:
    if _PROM_AVAILABLE:
        LLM_TOKENS.labels(role=role).inc(prompt + completion)

def generate_metrics() -> str:
    if not _PROM_AVAILABLE:
        return "# Prometheus metrics unavailable. Install: pip install prometheus_client\n"
    return generate_latest(registry).decode("utf-8")

def get_content_type() -> str:
    return CONTENT_TYPE_LATEST if _PROM_AVAILABLE else "text/plain"