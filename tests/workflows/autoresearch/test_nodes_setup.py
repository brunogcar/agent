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

import hashlib
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


# ===========================================================================
# [v1.9 A2] 6-col TSV with content_hash + corrupt-row warning (minimax Bug #2)
# ===========================================================================


class TestResumeDedupContentHash:
    """[v1.9 A2] The TSV header now has a 6th content_hash column so dedup
    survives resume. _load_history_from_ledger parses 6 cols; legacy 5-col
    ledgers load with content_hash="". Corrupt rows (<5 cols) log a warning.
    """

    def test_ledger_has_six_columns_with_content_hash(self, ar_state, tmp_path):
        """Write a row via node_log, read back, verify 6 tab-separated fields."""
        from workflows.autoresearch_impl.nodes.log import node_log
        results_path = tmp_path / "results.tsv"
        results_path.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n",
            encoding="utf-8",
        )
        state = dict(ar_state)
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["experiment_history"] = []
        state["current_experiment"] = {
            "iteration": 1, "description": "test", "metric": 0.42,
            "status": "keep", "commit": "abc123", "content_hash": "deadbeef",
        }
        node_log(state)
        content = results_path.read_text(encoding="utf-8")
        # The data row (last non-header line) must have 6 tab-separated fields.
        data_lines = [l for l in content.splitlines() if l and not l.startswith("iteration")]
        assert len(data_lines) == 1
        fields = data_lines[0].split("\t")
        assert len(fields) == 6
        assert fields[5] == "deadbeef"

    def test_load_history_parses_content_hash_column(self, tmp_path):
        """6-col ledger → history entries have content_hash populated."""
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        ledger = tmp_path / "results.tsv"
        ledger.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.5\tkeep\tfirst\th1\n"
            "2\tdef\t0.45\tkeep\tsecond\th2\n",
            encoding="utf-8",
        )
        history = _load_history_from_ledger(str(ledger))
        assert len(history) == 2
        assert history[0]["content_hash"] == "h1"
        assert history[1]["content_hash"] == "h2"

    def test_load_history_handles_legacy_five_col_ledger(self, tmp_path):
        """5-col ledger (legacy v1.8 format) → history entries have content_hash=''."""
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        ledger = tmp_path / "results.tsv"
        ledger.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\n"
            "1\tabc\t0.5\tkeep\tfirst\n"
            "2\tdef\t0.45\tkeep\tsecond\n",
            encoding="utf-8",
        )
        history = _load_history_from_ledger(str(ledger))
        assert len(history) == 2
        # Legacy 5-col ledgers default content_hash to "" (no dedup against old rows).
        assert history[0]["content_hash"] == ""
        assert history[1]["content_hash"] == ""

    def test_load_history_warns_on_corrupt_row(self, tmp_path):
        """Ledger with a row having only 3 cols → tracer.warning called,
        valid rows still loaded."""
        from workflows.autoresearch_impl.nodes.setup import _load_history_from_ledger
        ledger = tmp_path / "results.tsv"
        ledger.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.5\tkeep\tfirst\th1\n"
            "CORRUPT\tROW\tONLY\n"  # only 3 cols
            "2\tdef\t0.45\tkeep\tsecond\th2\n",
            encoding="utf-8",
        )
        with patch("workflows.autoresearch_impl.nodes.setup.tracer.warning") as mock_warn:
            history = _load_history_from_ledger(str(ledger), tid="t1")
        # 2 valid rows loaded (the corrupt one was skipped).
        assert len(history) == 2
        assert history[0]["iteration"] == 1
        assert history[1]["iteration"] == 2
        # tracer.warning was called at least once for the corrupt row.
        assert mock_warn.called
        warn_msg = mock_warn.call_args[0][2]
        assert "3 columns" in warn_msg or "has 3" in warn_msg


# ===========================================================================
# [v1.9 B1] Resume convergence counters recompute (qwen P1-2)
# ===========================================================================


class TestResumeConvergenceCounters:
    """[v1.9 B1] On resume, consecutive_discards is recomputed by scanning
    the tail of the reloaded history. Pre-v1.9 it was reset to 0.
    """

    def test_resume_recomputes_consecutive_discards(self, ar_state, tmp_path):
        """Ledger with last 4 rows = discard → resumed state has
        consecutive_discards=4."""
        from workflows.autoresearch_impl.nodes.setup import node_setup
        ar_state["resume"] = True
        ar_state["current_best"] = 0.42
        ar_state["baseline_metric"] = 0.50
        ar_state["branch"] = "autoresearch/existing"
        ar_state["project_root"] = str(tmp_path)
        ar_state["results_path"] = str(tmp_path / "results.tsv")
        # 1 keep + 4 discards at the tail.
        (tmp_path / "results.tsv").write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.42\tkeep\tfirst\th1\n"
            "2\t\t0.50\tdiscard\tbad1\th2\n"
            "3\t\t0.51\tdiscard\tbad2\th3\n"
            "4\t\t0.52\tdiscard\tbad3\th4\n"
            "5\t\t0.53\tdiscard\tbad4\th5\n",
            encoding="utf-8",
        )

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True):
            result = node_setup(ar_state)

        assert result["consecutive_discards"] == 4
        assert result["status"] == "running"

    def test_resume_recomputes_consecutive_discards_mixed_tail(self, ar_state, tmp_path):
        """Mixed tail (keep, discard, discard) → consecutive_discards=2."""
        from workflows.autoresearch_impl.nodes.setup import node_setup
        ar_state["resume"] = True
        ar_state["current_best"] = 0.42
        ar_state["baseline_metric"] = 0.50
        ar_state["branch"] = "autoresearch/existing"
        ar_state["project_root"] = str(tmp_path)
        ar_state["results_path"] = str(tmp_path / "results.tsv")
        # keep, discard, discard at the tail.
        (tmp_path / "results.tsv").write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.42\tkeep\tfirst\th1\n"
            "2\t\t0.50\tdiscard\tbad1\th2\n"
            "3\t\t0.51\tdiscard\tbad2\th3\n",
            encoding="utf-8",
        )

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True):
            result = node_setup(ar_state)

        assert result["consecutive_discards"] == 2


# ===========================================================================
# [v1.9 B2] Stale parallel dir cleanup (qwen P1-3)
# ===========================================================================


class TestStaleParallelDirCleanup:
    """[v1.9 B2] node_setup cleans up any stale {project_root}/.autoresearch/
    parallel/ dir from a prior crashed run BEFORE creating a new branch.
    """

    def test_setup_cleans_stale_parallel_dir(self, ar_state, tmp_path):
        """Pre-create {project_root}/.autoresearch/parallel/0/train.py with
        junk content, call node_setup (resume=False, mocked baseline),
        verify the dir is gone after setup."""
        from workflows.autoresearch_impl.nodes.setup import node_setup
        # Pre-create the stale parallel dir.
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        (parallel_dir / "0").mkdir(parents=True)
        (parallel_dir / "0" / "train.py").write_text("# junk from prior crash\n",
                                                      encoding="utf-8")
        assert parallel_dir.exists()

        ar_state["resume"] = False
        ar_state["project_root"] = str(tmp_path)
        ar_state["results_path"] = str(tmp_path / "results.tsv")
        ar_state["target_file"] = "train.py"

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True), \
             patch("workflows.autoresearch_impl.nodes.setup._run_experiment_subprocess",
                   return_value="val_bpb: 0.5"):
            node_setup(ar_state)

        # The stale parallel dir must be gone.
        assert not parallel_dir.exists(), "stale parallel dir was NOT cleaned up"


# ===========================================================================
# [v1.9 C4] seen_hashes dedup field (qwen P2-1)
# ===========================================================================


class TestSeenHashesDedup:
    """[v1.9 C4] seen_hashes is a list[str] (capped at 1000) that survives
    the 100-entry experiment_history cap. node_modify checks it for dedup.
    """

    def test_dedup_uses_seen_hashes_after_history_cap(self, ar_state):
        """History has 100 entries (capped), seen_hashes has the entry #5 hash
        (evicted from history). New proposal's hash matches → modify returns
        status='failed' with 'duplicate' error."""
        from workflows.autoresearch_impl.nodes.modify import node_modify
        dup_content = "print('dup')\n"
        dup_hash = hashlib.md5(dup_content.encode()).hexdigest()
        # History is full (100 entries) — entry #5's hash was evicted.
        history = [
            {"iteration": i, "content_hash": f"old_hash_{i}", "status": "discard"}
            for i in range(100)
        ]
        # But seen_hashes still has the evicted hash.
        seen_hashes = [f"old_hash_{i}" for i in range(100)] + [dup_hash]
        ar_state["current_experiment"] = {
            "new_content": dup_content, "description": "test",
        }
        ar_state["experiment_history"] = history
        ar_state["seen_hashes"] = seen_hashes

        result = node_modify(ar_state)
        assert result["status"] == "failed"
        assert "duplicate" in result["error"].lower()

    def test_seen_hashes_capped_at_1000(self, ar_state, tmp_path):
        """Append 1001 hashes → list stays at 1000 (oldest evicted)."""
        from workflows.autoresearch_impl.nodes.log import node_log
        results_path = tmp_path / "results.tsv"
        results_path.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n",
            encoding="utf-8",
        )
        state = dict(ar_state)
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["experiment_history"] = []
        # Pre-fill seen_hashes with 1000 entries.
        state["seen_hashes"] = [f"hash_{i}" for i in range(1000)]
        # The new proposal adds one more hash.
        state["current_experiment"] = {
            "iteration": 1, "description": "new", "metric": 0.42,
            "status": "keep", "commit": "abc", "content_hash": "new_hash_1001",
        }
        result = node_log(state)
        assert len(result["seen_hashes"]) == 1000
        # The newest hash is present; the oldest was evicted.
        assert "new_hash_1001" in result["seen_hashes"]
        assert "hash_0" not in result["seen_hashes"]

    def test_resume_populates_seen_hashes_from_ledger(self, ar_state, tmp_path):
        """Resume path extracts content_hash from each reloaded row →
        seen_hashes has 1 entry per row with non-empty hash."""
        from workflows.autoresearch_impl.nodes.setup import node_setup
        ar_state["resume"] = True
        ar_state["current_best"] = 0.42
        ar_state["baseline_metric"] = 0.50
        ar_state["branch"] = "autoresearch/existing"
        ar_state["project_root"] = str(tmp_path)
        ar_state["results_path"] = str(tmp_path / "results.tsv")
        # 3 rows: 2 with hashes, 1 with empty hash (failed-proposal placeholder).
        (tmp_path / "results.tsv").write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n"
            "1\tabc\t0.42\tkeep\tfirst\th1\n"
            "2\t\t0.50\tdiscard\tbad\t\n"
            "3\tdef\t0.45\tkeep\tthird\th3\n",
            encoding="utf-8",
        )

        with patch("workflows.autoresearch_impl.nodes.setup._git_create_branch",
                   return_value=True):
            result = node_setup(ar_state)

        # 2 non-empty hashes → seen_hashes has 2 entries (h1, h3), deduped.
        assert len(result["seen_hashes"]) == 2
        assert "h1" in result["seen_hashes"]
        assert "h3" in result["seen_hashes"]
