"""Agent tool tests — per-role metrics collection."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.metrics import _get_metrics, _clear_metrics


class TestPerRoleMetrics:
    """Test in-memory metrics collection for agent calls."""

    def setup_method(self):
        from tools.agent_ops.cache import _clear_cache
        _clear_cache()
        _clear_metrics()

    def test_metrics_recorded_on_success(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="classify", task="test")

        metrics = _get_metrics("classify")
        assert metrics["calls"] == 1
        assert metrics["successes"] == 1
        assert metrics["failures"] == 0
        assert metrics["total_elapsed"] >= 0

    def test_metrics_recorded_on_failure(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Timeout"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="code", task="test")

        metrics = _get_metrics("code")
        assert metrics["calls"] == 1
        assert metrics["successes"] == 0
        assert metrics["failures"] == 1

    def test_metrics_separate_by_role(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="classify", task="test1")
            agent(action="dispatch", role="route", task="test2")

        classify_m = _get_metrics("classify")
        route_m = _get_metrics("route")
        assert classify_m["calls"] == 1
        assert route_m["calls"] == 1

    def test_metrics_returns_all_when_no_role(self, mock_llm_result):
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="classify", task="test")

        all_metrics = _get_metrics()
        assert "classify" in all_metrics

    def test_metrics_meta_role(self, mock_llm_result):
        """agent(action='metrics') returns collected metrics."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="classify", task="test")

        result = agent(action="metrics", task="classify")
        assert result["status"] == "success"
        assert "metrics" in result
        assert result["metrics"]["calls"] == 1


class TestMetricsPersistence:
    """Metrics JSONL persistence (Bug #20).

    Metrics are appended to .agent_metrics.jsonl in the workspace root on
    each call, so they survive process restarts. Set AGENT_METRICS_PERSIST=0
    to disable.
    """

    def test_metrics_appended_to_jsonl(self, tmp_path, monkeypatch):
        """_record_metric should append to .agent_metrics.jsonl."""
        from unittest.mock import patch, MagicMock
        from tools.agent_ops import metrics as metrics_mod
        from tools.agent_ops.metrics import _record_metric

        # Reset persistence cache so it re-reads cfg
        monkeypatch.setattr(metrics_mod, "_METRICS_LOG_PATH", None)
        monkeypatch.setattr(metrics_mod, "_PERSIST_ENABLED", None)

        fake_cfg = MagicMock()
        fake_cfg.workspace_root = str(tmp_path)
        with patch("core.config.cfg", fake_cfg):
            _record_metric("test_role", "success", 0.5, 100, False)

            log_path = tmp_path / ".agent_metrics.jsonl"
            assert log_path.exists(), "Metrics JSONL file must be created"
            content = log_path.read_text()
            assert "test_role" in content
            assert "success" in content

    def test_persistence_disabled_when_env_var_zero(self, tmp_path, monkeypatch):
        """AGENT_METRICS_PERSIST=0 must disable persistence."""
        from unittest.mock import patch, MagicMock
        from tools.agent_ops import metrics as metrics_mod
        from tools.agent_ops.metrics import _record_metric

        monkeypatch.setattr(metrics_mod, "_METRICS_LOG_PATH", None)
        monkeypatch.setattr(metrics_mod, "_PERSIST_ENABLED", None)
        monkeypatch.setenv("AGENT_METRICS_PERSIST", "0")

        fake_cfg = MagicMock()
        fake_cfg.workspace_root = str(tmp_path)
        with patch("core.config.cfg", fake_cfg):
            _record_metric("test_role", "success", 0.5, 100, False)

            log_path = tmp_path / ".agent_metrics.jsonl"
            assert not log_path.exists(), "Persistence must be disabled when AGENT_METRICS_PERSIST=0"


class TestMetricsAggregation:
    """_get_aggregate_metrics returns cross-role totals (Bug #24)."""

    def test_aggregate_metrics_returns_totals(self):
        from tools.agent_ops.metrics import _record_metric, _get_aggregate_metrics
        _record_metric("role_a", "success", 1.0, 100)
        _record_metric("role_a", "error", 2.0, 50)
        _record_metric("role_b", "success", 3.0, 200)

        agg = _get_aggregate_metrics()
        assert agg["total_calls"] == 3
        assert agg["total_successes"] == 2
        assert agg["total_failures"] == 1
        assert agg["overall_success_rate"] == 2 / 3
        assert agg["avg_latency"] == (1.0 + 2.0 + 3.0) / 3
        assert agg["total_tokens"] == 350
        assert agg["roles_tracked"] == 2

    def test_aggregate_metrics_empty_returns_zeros(self):
        from tools.agent_ops.metrics import _get_aggregate_metrics
        agg = _get_aggregate_metrics()
        assert agg["total_calls"] == 0
        assert agg["overall_success_rate"] == 0.0
        assert agg["avg_latency"] == 0.0
        assert agg["roles_tracked"] == 0
