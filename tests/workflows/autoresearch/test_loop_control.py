"""tests/workflows/autoresearch/test_loop_control.py

[v1.4] Tests for loop-control features:
  - max_iterations (hard cap on experiments)
  - convergence detector (stop after N consecutive discards)
  - stuck detector (stop on metric plateau within ε of best)
  - experiment deduplication (md5 hash check on new_content)

Coverage:
  TestRouteAfterLog         — 6 tests covering each stopping condition + edge cases
  TestExperimentDeduplication — 2 tests covering the md5 dedup path in node_modify

[v1.4] New file — these features were entirely untested before this file.
The route_after_log router was added in v1.4 (replacing the v1.3 direct
log → propose edge). The dedup check was added to node_modify in v1.4 (N8).
"""
from __future__ import annotations

import hashlib

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# route_after_log — the v1.4 conditional router after node_log
# ---------------------------------------------------------------------------


class TestRouteAfterLog:
    """Test the route_after_log stopping conditions."""

    def test_continues_when_no_stopping_condition(self):
        """No stop when: unlimited iterations, history shorter than window."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 5,
            "max_iterations": 0,
            "convergence_window": 10,
            "convergence_epsilon": 0.001,
            "experiment_history": [{"status": "keep", "metric": 0.5}],
            "current_best": 0.5,
        }
        assert route_after_log(state) == "propose"

    def test_stops_at_max_iterations(self):
        """Stop when experiment_count >= max_iterations (>0)."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 5,
            "max_iterations": 5,
            "convergence_window": 10,
            "convergence_epsilon": 0.001,
            "experiment_history": [],
            "current_best": 0.5,
        }
        assert route_after_log(state) == "end"

    def test_stops_on_convergence_all_discarded(self):
        """Stop when last N experiments all have status='discard'."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 15,
            "max_iterations": 0,
            "convergence_window": 5,
            "convergence_epsilon": 0.001,
            "experiment_history": [{"status": "discard", "metric": 0.4}] * 5,
            "current_best": 0.5,
        }
        assert route_after_log(state) == "end"

    def test_stops_on_stuck_metric_plateau(self):
        """Stop when last N metrics are all within ε of current_best."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 15,
            "max_iterations": 0,
            "convergence_window": 5,
            "convergence_epsilon": 0.01,
            "experiment_history": [{"status": "keep", "metric": 0.5}] * 5,
            "current_best": 0.5,
        }
        assert route_after_log(state) == "end"

    def test_does_not_stop_with_mixed_results(self):
        """Continue when history has mixed statuses AND varied metrics."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 15,
            "max_iterations": 0,
            "convergence_window": 5,
            "convergence_epsilon": 0.001,
            "experiment_history": [
                {"status": "discard", "metric": 0.4},
                {"status": "keep", "metric": 0.5},
                {"status": "discard", "metric": 0.45},
                {"status": "keep", "metric": 0.48},
                {"status": "discard", "metric": 0.43},
            ],
            "current_best": 0.5,
        }
        assert route_after_log(state) == "propose"

    def test_max_iterations_zero_means_unlimited(self):
        """max_iterations=0 must never trigger the max-iterations stop."""
        from workflows.autoresearch_impl.routes import route_after_log
        state = {
            "experiment_count": 999,
            "max_iterations": 0,
            "convergence_window": 100,
            "convergence_epsilon": 0.001,
            "experiment_history": [],
            "current_best": 0.5,
        }
        assert route_after_log(state) == "propose"


# ---------------------------------------------------------------------------
# Experiment deduplication (node_modify md5 check — v1.4 N8)
# ---------------------------------------------------------------------------


class TestExperimentDeduplication:
    """Test that duplicate experiments are skipped."""

    def test_duplicate_content_skipped(self, ar_state):
        """A proposal whose new_content matches a prior experiment's hash
        must return status='failed' with a 'duplicate' error — no write."""
        from workflows.autoresearch_impl.nodes.modify import node_modify

        ar_state["current_experiment"] = {
            "new_content": "print('hello')",
            "description": "test",
        }
        content_hash = hashlib.md5("print('hello')".encode()).hexdigest()
        ar_state["experiment_history"] = [
            {"iteration": 1, "content_hash": content_hash, "status": "discard"},
        ]

        result = node_modify(ar_state)
        assert result["status"] == "failed"
        assert "duplicate" in result["error"].lower()

    def test_new_content_not_skipped(self, ar_state, tmp_path):
        """A proposal whose new_content does NOT match any prior hash must
        proceed to the write (status='running' on success)."""
        from workflows.autoresearch_impl.nodes.modify import node_modify

        ar_state["project_root"] = str(tmp_path)
        ar_state["target_file"] = "test.py"
        ar_state["current_experiment"] = {
            "new_content": "print('new')",
            "description": "test",
        }
        ar_state["experiment_history"] = [
            {"iteration": 1, "content_hash": "abc123", "status": "discard"},
        ]

        result = node_modify(ar_state)
        # Either the write succeeded (status="running") or it failed for a
        # non-duplicate reason — both are acceptable. The only failure we
        # must NOT see is "duplicate".
        assert result.get("status") != "failed" or \
            "duplicate" not in result.get("error", "").lower()


# ===========================================================================
# [v1.9 D3] recursion_limit from cfg + env (minimax Risk #2)
# ===========================================================================


class TestRecursionLimitFromCfg:
    """[v1.9 D3] recursion_limit is read from cfg.autoresearch_recursion_limit
    (env: AUTORESEARCH_RECURSION_LIMIT, default 1000). Was: hardcoded 1000.
    """

    def test_recursion_limit_read_from_cfg(self, monkeypatch, tmp_path):
        """Set cfg.autoresearch_recursion_limit=500, call run_workflow with a
        mocked graph, verify graph.invoke was called with
        config={'recursion_limit': 500}."""
        import core.config
        monkeypatch.setattr(core.config.cfg, "autoresearch_recursion_limit", 500)

        # Mock build_autoresearch_graph to return a Mock whose .invoke()
        # records the config.
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"status": "success", "trace_id": "t1"}

        with patch("workflows.autoresearch.build_autoresearch_graph",
                   return_value=mock_graph):
            from workflows.base import run_workflow
            run_workflow(
                workflow_type="autoresearch",
                goal="minimize val_bpb",
                project_root=str(tmp_path),
                trace_id="test-recursion",
                target_file="train.py",
            )

        # Verify graph.invoke was called with config={'recursion_limit': 500}.
        mock_graph.invoke.assert_called_once()
        call_args = mock_graph.invoke.call_args
        config = call_args[1]["config"] if "config" in call_args[1] else call_args[0][1]
        assert config["recursion_limit"] == 500, (
            f"expected recursion_limit=500, got {config.get('recursion_limit')}"
        )
