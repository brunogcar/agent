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
        # [v1.9-V2] Also clears pre_extracted_metrics (plural) — stale list from a
        # prior parallel iteration would mislead parallel evaluate.
        assert result == {"experiment_output": "prior output\n", "pre_extracted_metric": None, "pre_extracted_metrics": []}
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
    """[v1.11 A7] run_target_subprocess now uses Popen + process-group kill
    (was: subprocess.run). Tests updated to mock Popen + communicate."""

    def test_success_returns_combined_output(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.return_value = ("out\n", "")
        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc):
            assert run_target_subprocess("train.py", "/proj", 60) == "out\n"

    def test_timeout_appends_sentinel_and_partial_output(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        # First communicate() raises TimeoutExpired, second (post-kill) returns partial.
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["x"], timeout=60),
            ("partial", "err"),
        ]
        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc), \
             patch("workflows.autoresearch_impl.helpers._kill_process_tree"):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "partial" in out
        assert "err" in out
        assert "timed out after 60s" in out

    def test_filenotfound_returns_clear_error(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   side_effect=FileNotFoundError(2, "no train.py")):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "target_file not found: train.py" in out

    def test_generic_exception_returns_error_message(self):
        from workflows.autoresearch_impl.helpers import run_target_subprocess
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = PermissionError("denied")
        with patch("workflows.autoresearch_impl.helpers.subprocess.Popen",
                   return_value=mock_proc), \
             patch("workflows.autoresearch_impl.helpers._kill_process_tree"):
            out = run_target_subprocess("train.py", "/proj", 60)
        assert "experiment crashed" in out
        assert "PermissionError" in out
        assert "denied" in out


# ===========================================================================
# [v1.9 D1] Log dir relocation to .autoresearch/logs/ (user request)
# ===========================================================================


class TestLogDirRelocation:
    """[v1.9 D1] Log dir moved from {results_path}.d/ to
    {project_root}/.autoresearch/logs/. User explicitly requested: "we use
    logs/ if needed, create subfolder there more descriptive than .d/".
    """

    def test_log_dir_is_autoresearch_logs_not_d_suffix(self, ar_state, tmp_path):
        """Verify the log file is written to
        {project_root}/.autoresearch/logs/{iteration}.log, NOT
        {results_path}.d/{iteration}.log."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        results_path = tmp_path / "results.tsv"
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.42\n"):
            node_run_experiment(state)

        # The log file must be under .autoresearch/logs/, NOT results.tsv.d/
        log_dir = tmp_path / ".autoresearch" / "logs"
        assert log_dir.exists(), f"log dir {log_dir} not created"
        assert (log_dir / "1.log").exists(), "log file 1.log not created"
        # The OLD .d/ location must NOT exist.
        assert not (tmp_path / "results.tsv.d").exists(), (
            "old {results_path}.d/ dir should NOT exist after v1.9 relocation"
        )


# ===========================================================================
# [v1.9 D2] Log rotation / size cap (minimax Risk #1)
# ===========================================================================


class TestLogRotationCap:
    """[v1.9 D2] When .autoresearch/logs/ exceeds
    cfg.autoresearch_log_dir_max_mb, new log writes are SKIPPED + a
    tracer.warning is emitted.
    """

    def test_log_write_skipped_when_dir_exceeds_cap(self, ar_state, tmp_path, monkeypatch):
        """Pre-populate .autoresearch/logs/ with files totaling >1MB, set
        cfg.autoresearch_log_dir_max_mb=1, call _write_full_output_log →
        no new file written + tracer.warning called."""
        from workflows.autoresearch_impl.nodes.run_experiment import _write_full_output_log
        import core.config
        # Set the cap to 1MB.
        monkeypatch.setattr(core.config.cfg, "autoresearch_log_dir_max_mb", 1)
        # Pre-populate the log dir with a 2MB file.
        results_path = tmp_path / "results.tsv"
        log_dir = tmp_path / ".autoresearch" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "big.log").write_text("X" * (2 * 1024 * 1024), encoding="utf-8")

        with patch("workflows.autoresearch_impl.nodes.run_experiment.tracer.warning") as mock_warn:
            _write_full_output_log(str(results_path), 5, "new output\n")

        # No new log file should be created.
        assert not (log_dir / "5.log").exists()
        # tracer.warning was called.
        assert mock_warn.called
