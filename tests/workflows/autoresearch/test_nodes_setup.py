"""tests/workflows/autoresearch/test_nodes_setup.py

Per-node tests for setup, evaluate, and the shared helpers (extract_metric,
run_target_subprocess) defined in `workflows/autoresearch_impl/helpers.py`.

Coverage:
  node_setup            — branch+ledger+baseline (happy), baseline failure
  node_evaluate         — extract last metric, missing metric, prior failure skip
  extract_metric        — `:`/`=`/whitespace separators, sci notation,
                          no-match, last-occurrence, special chars in name
  run_target_subprocess — success, timeout sentinel, FileNotFoundError,
                          generic exception

[v1.3 tests] New file — fills the per-node coverage gap left by
test_loop_integration.py (which only had 1 evaluate test + 1 missing-metric
test). The helper unit tests for extract_metric + run_target_subprocess
were entirely missing before this file.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# extract_metric (helper)
# ---------------------------------------------------------------------------


class TestExtractMetric:
    def test_colon_separator(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("val_bpb: 0.42", "val_bpb") == 0.42

    def test_equals_separator(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("val_bpb=0.42", "val_bpb") == 0.42

    def test_whitespace_around_separator(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        # The regex requires a `:` or `=` separator (with optional whitespace
        # around it) — pure whitespace alone is NOT a valid separator.
        assert extract_metric("val_bpb : 0.42", "val_bpb") == 0.42
        assert extract_metric("val_bpb 0.42", "val_bpb") is None

    def test_scientific_notation(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("loss: 1.5e-3", "loss") == 1.5e-3

    def test_negative_value(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("delta: -0.5", "delta") == -0.5

    def test_no_match_returns_none(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("training complete", "val_bpb") is None

    def test_last_occurrence(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        out = "epoch 0: val_bpb: 0.50\nepoch 1: val_bpb: 0.42\n"
        assert extract_metric(out, "val_bpb") == 0.42

    def test_special_chars_in_metric_name(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("val/loss: 0.7", "val/loss") == 0.7

    def test_empty_inputs_return_none(self):
        from workflows.autoresearch_impl.helpers import extract_metric
        assert extract_metric("", "val_bpb") is None
        assert extract_metric("val_bpb: 0.42", "") is None


# ---------------------------------------------------------------------------
# run_target_subprocess (helper)
# ---------------------------------------------------------------------------


class TestRunTargetSubprocess:
    def test_success_returns_combined_output(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        fake = MagicMock(stdout="ok\n", stderr="warn\n", returncode=0)
        with patch("workflows.autoresearch_impl.helpers.subprocess.run", return_value=fake) as m:
            out = run_target_subprocess("train.py", "/proj", 30)
        assert "ok" in out and "warn" in out
        m.assert_called_once()

    def test_timeout_returns_sentinel(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        exc = subprocess.TimeoutExpired(cmd=["x"], timeout=30)
        exc.stdout = "partial out"
        exc.stderr = "partial err"
        with patch("workflows.autoresearch_impl.helpers.subprocess.run", side_effect=exc):
            out = run_target_subprocess("train.py", "/proj", 30)
        assert "partial out" in out
        assert "timed out after 30s" in out

    def test_filenotfound_returns_clear_error(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   side_effect=FileNotFoundError(2, "no such file")):
            out = run_target_subprocess("missing.py", "/proj", 30)
        assert "target_file not found: missing.py" in out

    def test_generic_exception_returns_error_message(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        with patch("workflows.autoresearch_impl.helpers.subprocess.run",
                   side_effect=OSError("disk full")):
            out = run_target_subprocess("train.py", "/proj", 30)
        assert "experiment crashed" in out
        assert "disk full" in out


# ---------------------------------------------------------------------------
# node_setup
# ---------------------------------------------------------------------------


class TestNodeSetup:
    def test_baseline_success_sets_metric_and_writes_ledger(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.setup import node_setup
        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch", return_value=True), \
             patch("workflows.autoresearch_impl.nodes.setup._run_experiment_subprocess",
                   return_value="val_bpb: 0.50\n"):
            result = node_setup(ar_state)
        assert result["baseline_metric"] == 0.50
        assert result["current_best"] == 0.50
        assert result["status"] == "running"
        assert result["results_path"] == ar_state["results_path"]
        ledger = (tmp_path / "results.tsv").read_text(encoding="utf-8")
        assert ledger.startswith("iteration\tcommit\tmetric\tstatus\tdescription")

    def test_baseline_metric_missing_returns_failed(self, ar_state):
        from workflows.autoresearch_impl.nodes.setup import node_setup
        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch", return_value=True), \
             patch("workflows.autoresearch_impl.nodes.setup._run_experiment_subprocess",
                   return_value="training done\n"):
            result = node_setup(ar_state)
        assert result["status"] == "failed"
        assert "not found" in result["error"]
        assert result["baseline_metric"] == 0.0
        assert result["current_best"] == 0.0


# ---------------------------------------------------------------------------
# node_evaluate
# ---------------------------------------------------------------------------


class TestNodeEvaluate:
    def test_extracts_last_metric_occurrence(self, ar_state):
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state.update({
            "experiment_output": (
                "epoch 0: val_bpb: 0.50\n"
                "epoch 1: val_bpb: 0.45\n"
                "epoch 2: val_bpb: 0.42\n"
            ),
            "metric_name": "val_bpb",
            "status": "running",
        })
        result = node_evaluate(state)
        assert result["current_metric"] == 0.42
        assert result["status"] == "running"

    def test_metric_missing_returns_failed(self, ar_state):
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state.update({
            "experiment_output": "training complete\n",
            "metric_name": "val_bpb",
            "status": "running",
        })
        result = node_evaluate(state)
        assert result["status"] == "failed"
        assert "not found" in result["error"]
        assert result["current_metric"] == 0.0

    def test_prior_failure_skips_evaluation(self, ar_state):
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state.update({
            "experiment_output": "val_bpb: 0.42\n",  # would normally match
            "metric_name": "val_bpb",
            "status": "failed",
        })
        result = node_evaluate(state)
        # Skip path: only returns current_metric, no status change.
        assert result == {"current_metric": 0.0}
