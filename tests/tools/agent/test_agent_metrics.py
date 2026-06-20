"""Agent tool tests — per-role metrics collection."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.metrics import _get_metrics, _clear_metrics


class TestPerRoleMetrics:
    """Test in-memory metrics collection for agent calls."""

    def setup_method(self):
        from tools.agent_core.cache import _clear_cache
        _clear_cache()
        _clear_metrics()

    def test_metrics_recorded_on_success(self, mock_llm_result):
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="classify", task="test")

        metrics = _get_metrics("classify")
        assert metrics["calls"] == 1
        assert metrics["successes"] == 1
        assert metrics["failures"] == 0
        assert metrics["total_elapsed"] >= 0

    def test_metrics_recorded_on_failure(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Timeout"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="code", task="test")

        metrics = _get_metrics("code")
        assert metrics["calls"] == 1
        assert metrics["successes"] == 0
        assert metrics["failures"] == 1

    def test_metrics_separate_by_role(self, mock_llm_result):
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="classify", task="test1")
            agent(role="route", task="test2")

        classify_m = _get_metrics("classify")
        route_m = _get_metrics("route")
        assert classify_m["calls"] == 1
        assert route_m["calls"] == 1

    def test_metrics_returns_all_when_no_role(self, mock_llm_result):
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="classify", task="test")

        all_metrics = _get_metrics()
        assert "classify" in all_metrics

    def test_metrics_meta_role(self, mock_llm_result):
        """agent(role='metrics') returns collected metrics."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="classify", task="test")

        result = agent(role="metrics", task="classify")
        assert result["status"] == "success"
        assert "metrics" in result
        assert result["metrics"]["calls"] == 1
