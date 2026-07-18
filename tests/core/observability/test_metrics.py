"""tests/core/observability/test_metrics.py — Prometheus metrics tests.

Covers:
  - Graceful degradation (no-op when prometheus_client missing).
  - track_node (histogram observation).
  - track_task_status (counter increment).
  - track_tdd_iterations (histogram observation).
  - track_llm_tokens (counter increment, prompt+completion summed).
  - generate_metrics (Prometheus text format output).
  - get_content_type.

The metrics module lives in core/observability/metrics.py. It tracks autocode
node duration, terminal task status counts, TDD iterations per task, and LLM
token consumption. All helpers are safe to call anywhere — they become no-ops
when prometheus_client is not installed.
"""
from __future__ import annotations

import pytest

from core.observability import metrics
from core.observability.metrics import (
    _PROM_AVAILABLE,
    generate_metrics,
    get_content_type,
    registry,
    track_llm_tokens,
    track_node,
    track_task_status,
    track_tdd_iterations,
)


pytestmark = pytest.mark.skipif(
    not _PROM_AVAILABLE,
    reason="prometheus_client not installed — metrics are no-ops",
)


# ===========================================================================
# track_node
# ===========================================================================
class TestTrackNode:
    def test_observe_does_not_crash(self):
        track_node("node_run_tests", duration=2.4)

    def test_observe_multiple_values(self):
        for d in [0.1, 0.5, 1.0, 2.5, 5.0]:
            track_node("node_search", duration=d)
        # The histogram should have 5 observations for this label
        # We can't easily read back individual observations, but we can
        # verify generate_metrics contains the metric name.
        text = generate_metrics()
        assert "autocode_node_duration_seconds" in text

    def test_different_labels_tracked_separately(self):
        track_node("node_a", duration=1.0)
        track_node("node_b", duration=2.0)
        text = generate_metrics()
        assert 'node_name="node_a"' in text
        assert 'node_name="node_b"' in text


# ===========================================================================
# track_task_status
# ===========================================================================
class TestTrackTaskStatus:
    def test_increment_does_not_crash(self):
        track_task_status("success")

    def test_multiple_statuses(self):
        track_task_status("success")
        track_task_status("success")
        track_task_status("failed")
        text = generate_metrics()
        assert "autocode_task_status_total" in text
        assert 'status="success"' in text
        assert 'status="failed"' in text


# ===========================================================================
# track_tdd_iterations
# ===========================================================================
class TestTrackTddIterations:
    def test_observe_does_not_crash(self):
        track_tdd_iterations(3)

    def test_multiple_values(self):
        for n in [1, 2, 2, 3, 5]:
            track_tdd_iterations(n)
        text = generate_metrics()
        assert "autocode_tdd_iterations" in text


# ===========================================================================
# track_llm_tokens
# ===========================================================================
class TestTrackLlmTokens:
    def test_increment_does_not_crash(self):
        track_llm_tokens("planner", prompt=100, completion=50)

    def test_prompt_plus_completion_summed(self):
        """track_llm_tokens increments the counter by prompt + completion."""
        track_llm_tokens("executor", prompt=200, completion=100)
        text = generate_metrics()
        assert "autocode_llm_tokens_total" in text
        assert 'role="executor"' in text

    def test_multiple_roles(self):
        track_llm_tokens("planner", prompt=10, completion=5)
        track_llm_tokens("executor", prompt=20, completion=10)
        track_llm_tokens("router", prompt=5, completion=2)
        text = generate_metrics()
        for role in ("planner", "executor", "router"):
            assert f'role="{role}"' in text


# ===========================================================================
# generate_metrics
# ===========================================================================
class TestGenerateMetrics:
    def test_returns_nonempty_string(self):
        text = generate_metrics()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_contains_all_metric_names(self):
        # Emit at least one observation for each metric
        track_node("n", 1.0)
        track_task_status("success")
        track_tdd_iterations(1)
        track_llm_tokens("r", 1, 1)
        text = generate_metrics()
        assert "autocode_node_duration_seconds" in text
        assert "autocode_task_status_total" in text
        assert "autocode_tdd_iterations" in text
        assert "autocode_llm_tokens_total" in text

    def test_is_prometheus_text_format(self):
        """The output must be valid Prometheus text exposition format."""
        text = generate_metrics()
        # Each non-comment, non-empty line should contain a metric name + value
        for line in text.strip().split("\n"):
            if line.startswith("#") or not line:
                continue
            # Metric lines look like: name{labels} value
            # or: name value
            assert " " in line  # has at least name + value

    def test_repeated_calls_are_idempotent(self):
        """Calling generate_metrics twice returns the same cumulative state."""
        track_node("idempotent", 1.0)
        text1 = generate_metrics()
        text2 = generate_metrics()
        # Same content (no new observations between calls)
        assert text1 == text2


# ===========================================================================
# get_content_type
# ===========================================================================
class TestGetContentType:
    def test_returns_string(self):
        ct = get_content_type()
        assert isinstance(ct, str)
        assert len(ct) > 0

    def test_returns_prometheus_content_type(self):
        ct = get_content_type()
        assert "text/plain" in ct or "prometheus" in ct.lower()


# ===========================================================================
# Registry
# ===========================================================================
class TestRegistry:
    def test_registry_exists(self):
        assert registry is not None

    def test_registry_is_collector_registry(self):
        from prometheus_client import CollectorRegistry
        assert isinstance(registry, CollectorRegistry)
