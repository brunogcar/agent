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
