"""tests/workflows/autoresearch/test_resume.py

[v1.7] Tests for resume support (N3) + checkpoint on keep (N7).

Coverage:
  TestResumeSetup          — node_setup skips baseline + branch creation on
                             resume; reloads experiment_history from results.tsv
  TestCheckpointOnKeep     — node_decide saves a checkpoint via
                             `save_checkpoint(tid, "keep", state)` on every
                             keep (single-experiment path); discard paths do
                             NOT checkpoint

Design notes:
  - The `ar_state` fixture (from conftest.py) provides a minimal autoresearch
    state pointing at a tmp project dir with `branch="autoresearch/test"` and
    `current_best=0.0`. Resume tests override `resume=True`, `current_best>0`,
    and `branch="autoresearch/existing"` to exercise the new v1.7 paths.
  - The non-resume test confirms the v1.6 baseline path is UNCHANGED — a
    regression guard ensuring `resume=False` (default) doesn't accidentally
    trigger the resume code path.
  - `save_checkpoint` is patched at the source module (`core.observability.
    checkpoint.save_checkpoint`) because `node_decide` imports it lazily
    inside the function (`from core.observability.checkpoint import
    save_checkpoint`). The patch resolves correctly because Python's `from
    X import Y` re-reads the attribute at import time.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Resume support — node_setup skips baseline + branch creation
# ---------------------------------------------------------------------------


class TestResumeSetup:
    """Test that setup skips baseline + branch creation on resume."""

    def test_resume_skips_baseline(self, ar_state, tmp_path):
        """[v1.7 N3] resume=True + current_best>0 + branch set → skip baseline.

        Verifies:
          - status is "running" (not "failed")
          - current_best is preserved (0.42) — NOT re-baselined
          - experiment_count is loaded from the ledger (1 row → 1)
          - experiment_history has 1 entry (from the ledger)
        """
        from workflows.autoresearch_impl.nodes.setup import node_setup
        ar_state["resume"] = True
        ar_state["current_best"] = 0.42
        ar_state["baseline_established"] = True  # [v1.11 A5] new flag
        ar_state["baseline_metric"] = 0.50
        ar_state["branch"] = "autoresearch/existing"
        ar_state["project_root"] = str(tmp_path)
        ar_state["results_path"] = str(tmp_path / "results.tsv")
        # Create a fake ledger with 1 prior experiment (v1.9 A2: 6-col format).
        (tmp_path / "results.tsv").write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc123\t0.42\tkeep\ttest change\th123\n",
            encoding="utf-8",
        )

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True):
            result = node_setup(ar_state)

        assert result["status"] == "running"
        assert result["current_best"] == 0.42  # NOT re-baselined
        assert result["experiment_count"] == 1  # loaded from ledger
        assert len(result.get("experiment_history", [])) == 1
        assert result["experiment_history"][0]["iteration"] == 1
        assert result["experiment_history"][0]["status"] == "keep"

    def test_non_resume_runs_baseline(self, ar_state, tmp_path):
        """[v1.7 N3 regression guard] resume=False → v1.6 behavior unchanged.

        Verifies the baseline runs (current_best set from baseline output)
        and experiment_count is 0 (no prior ledger rows). Without this test,
        a buggy `is_resume` check could accidentally skip baseline for fresh
        runs too.
        """
        from workflows.autoresearch_impl.nodes.setup import node_setup
        ar_state["resume"] = False
        ar_state["project_root"] = str(tmp_path)
        ar_state["target_file"] = "train.py"
        ar_state["results_path"] = str(tmp_path / "results.tsv")

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True), \
             patch("workflows.autoresearch_impl.nodes.setup._run_experiment_subprocess",
                   return_value="val_bpb: 0.5"):
            result = node_setup(ar_state)

        assert result["status"] == "running"
        assert result["current_best"] == 0.5  # fresh baseline
        assert result["experiment_count"] == 0  # no prior history

    def test_resume_reloads_history_from_ledger(self, tmp_path):
        """[v1.7 N3] _load_history_from_ledger parses TSV rows into dicts.

        Covers:
          - Header line skipped
          - Rows with empty commit (discard) parsed correctly
          - Numeric fields converted (iteration int, metric float)
          - All 3 rows returned in order
        """
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        # [v1.9 A2] 6-col ledger format (with content_hash).
        ledger = tmp_path / "results.tsv"
        ledger.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.5\tkeep\tfirst\th1\n"
            "2\t\t0.6\tdiscard\tsecond\t\n"
            "3\tdef\t0.45\tkeep\tthird\th3\n",
            encoding="utf-8",
        )
        history = _load_history_from_ledger(str(ledger))
        assert len(history) == 3
        assert history[0]["iteration"] == 1
        assert history[0]["status"] == "keep"
        assert history[0]["commit"] == "abc"
        assert history[0]["content_hash"] == "h1"  # [v1.9 A2] 6th column parsed
        assert history[1]["commit"] == ""  # discard row has empty commit
        assert history[1]["content_hash"] == ""  # empty hash
        assert history[2]["metric"] == 0.45
        assert history[2]["content_hash"] == "h3"

    def test_load_history_handles_missing_file(self, tmp_path):
        """[v1.7 N3] Missing ledger file → empty list (no crash)."""
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        history = _load_history_from_ledger(str(tmp_path / "nonexistent.tsv"))
        assert history == []

    def test_load_history_handles_empty_file(self, tmp_path):
        """[v1.7 N3] Empty ledger (just header) → empty list."""
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        ledger = tmp_path / "results.tsv"
        ledger.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n",
            encoding="utf-8",
        )
        history = _load_history_from_ledger(str(ledger))
        assert history == []


# ---------------------------------------------------------------------------
# Checkpoint on keep — node_decide saves a checkpoint after every commit
# ---------------------------------------------------------------------------


class TestCheckpointOnKeep:
    """Test that decide saves checkpoint on keep (and NOT on discard)."""

    def test_checkpoint_saved_on_keep(self, ar_state, tmp_path):
        """[v1.7 N7] Improvement → commit → save_checkpoint called once.

        The single-experiment keep path must call `save_checkpoint(tid,
        "keep", state)` exactly once after `_git_commit` returns a non-empty
        SHA. The state dict passed to save_checkpoint includes the updated
        `current_best` (= current_metric on keep).
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.4  # better than 0.5 (lower is better)
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["project_root"] = str(tmp_path)
        ar_state["current_experiment"] = {"description": "test", "iteration": 1}

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc123"), \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             patch("core.observability.checkpoint.save_checkpoint") as mock_save:
            node_decide(ar_state)

        mock_save.assert_called_once()
        # Verify the saved state has the updated current_best (not the old one).
        saved_state = mock_save.call_args[0][2]
        assert saved_state["current_best"] == 0.4

    def test_no_checkpoint_on_discard(self, ar_state, tmp_path):
        """[v1.7 N7] No improvement → discard → save_checkpoint NOT called.

        Discards represent a non-improvement — there's no recoverable state
        worth resuming from (the working tree is reset to the prior HEAD).
        Only keeps checkpoint.
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.6  # worse than 0.5
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["project_root"] = str(tmp_path)
        ar_state["current_experiment"] = {"description": "test", "iteration": 1}

        with patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             patch("core.observability.checkpoint.save_checkpoint") as mock_save:
            node_decide(ar_state)

        mock_save.assert_not_called()

    def test_no_checkpoint_on_empty_sha(self, ar_state, tmp_path):
        """[v1.7 N7] Improvement but commit failed (empty SHA) → no checkpoint.

        Mirrors v1.3 P1-1: empty SHA → discard. Since it's a discard, no
        checkpoint should be saved (the working tree is reset, no
        recoverable state).
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.4  # would be improvement
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["project_root"] = str(tmp_path)
        ar_state["current_experiment"] = {"description": "test", "iteration": 1}

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value=""), \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             patch("core.observability.checkpoint.save_checkpoint") as mock_save:
            node_decide(ar_state)

        mock_save.assert_not_called()
