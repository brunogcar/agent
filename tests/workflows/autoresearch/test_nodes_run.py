"""tests/workflows/autoresearch/test_nodes_run.py

Per-node tests for run_experiment + the shared run_target_subprocess helper
(as called from the run_experiment node).

Coverage:
  node_run_experiment    — success, prior-failure skip, output >50KB truncation
  run_target_subprocess  — success, timeout sentinel + partial output,
                           FileNotFoundError, generic exception

[v1.3 tests] New file — run_experiment had ZERO dedicated tests before this
file (the node was only exercised via the full-loop integration test). The
helper is also tested in test_nodes_setup.py (extract_metric + the helper
unit tests live there because setup is the first node to use them); this
file covers the run_experiment-specific call paths and the 50KB truncation
logic that only run_experiment.py performs.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# node_run_experiment
# ---------------------------------------------------------------------------


class TestNodeRunExperiment:
    def test_success_captures_experiment_output(self, ar_state):
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state["status"] = "running"
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.42\n"):
            result = node_run_experiment(state)
        assert result["experiment_output"] == "val_bpb: 0.42\n"
        assert result["status"] == "running"
        assert result["error"] == ""
        # [v1.8 N10] pre_extracted_metric should be set from the full output.
        assert result["pre_extracted_metric"] == 0.42

    def test_prior_failure_skips_run(self, ar_state):
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state.update({
            "status": "failed",  # modify failed
            "experiment_output": "prior output\n",
        })
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess") as m:
            result = node_run_experiment(state)
        # Skip path returns the prior experiment_output and does NOT call subprocess.
        # [v1.8 N10] Also clears pre_extracted_metric to None (no new run).
        assert result == {"experiment_output": "prior output\n", "pre_extracted_metric": None}
        m.assert_not_called()

    def test_output_over_50kb_is_truncated(self, ar_state):
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state["status"] = "running"
        big = "X" * 60_000  # 60KB > 50KB threshold
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value=big):
            result = node_run_experiment(state)
        # Truncated to last 50KB.
        assert len(result["experiment_output"]) == 50_000
        assert result["experiment_output"] == big[-50_000:]
        # [v1.8 N10] No metric in the output → pre_extracted_metric is None.
        assert result["pre_extracted_metric"] is None


# ---------------------------------------------------------------------------
# run_target_subprocess (helper) — run_experiment call paths
# ---------------------------------------------------------------------------


class TestRunTargetSubprocessForRun:
    def test_success_returns_combined_output(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        fake = MagicMock(stdout="out\n", stderr="", returncode=0)
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   return_value=fake):
            assert run_target_subprocess("train.py", "/proj", 60) == "out\n"

    def test_timeout_appends_sentinel_and_partial_output(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        exc = subprocess.TimeoutExpired(cmd=["x"], timeout=60)
        exc.stdout = "partial"
        exc.stderr = "err"
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   side_effect=exc):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "partial" in out
        assert "err" in out
        assert "timed out after 60s" in out

    def test_filenotfound_returns_clear_error(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   side_effect=FileNotFoundError(2, "no train.py")):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "target_file not found: train.py" in out

    def test_generic_exception_returns_error_message(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   side_effect=PermissionError("denied")):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "experiment crashed" in out
        assert "PermissionError" in out
        assert "denied" in out
