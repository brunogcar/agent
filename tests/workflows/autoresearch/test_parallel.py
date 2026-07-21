"""tests/workflows/autoresearch/test_parallel.py

[v1.6] Tests for the parallel-experiments (batch mode) feature.

Coverage:
  TestParallelBackwardCompat — parallel_count=1 behaves exactly as v1.5
                              (singular fields only; plural fields unused)
  TestParallelPropose        — parallel_count=N generates N proposals via
                              N parallel _call_planner calls
  TestParallelModify         — writes each proposal to its own temp dir
                              under {project_root}/.autoresearch/parallel/{i}/
  TestParallelRunExperiment  — runs N subprocesses in parallel; missing
                              temp files produce "skipped" sentinels
  TestParallelEvaluate       — extracts N metrics from N outputs
  TestParallelDecide         — picks the best, copies winner's content to
                              the real target_file, commits, cleans up
  TestParallelLog            — appends N ledger rows + N history entries

Design notes:
  - parallel_count=1 paths are unchanged from v1.5 — the existing per-node
    test files (test_nodes_propose, test_nodes_decide, etc.) already cover
    that behavior. This file only tests the parallel_count > 1 path.
  - The parallel path uses ThreadPoolExecutor — patching _call_planner /
    _run_subprocess / _git_commit at the module level works because the
    pool threads import those names lazily from the node module's globals.
  - The temp dir {project_root}/.autoresearch/parallel/{i}/ is created by
    node_modify and removed by node_decide (shutil.rmtree). Tests that
    exercise the full propose→modify→run→evaluate→decide chain must not
    leak temp dirs on failure (decide's rmtree runs on every exit path).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# parallel_count=1 backward compatibility
# ---------------------------------------------------------------------------


class TestParallelBackwardCompat:
    """parallel_count=1 must produce IDENTICAL behavior to v1.5.

    The v1.5 per-node tests already cover the single-experiment path; these
    tests just verify that setting parallel_count=1 explicitly doesn't
    accidentally activate the parallel path (e.g. by leaving plural fields
    populated when they shouldn't be, or vice versa).
    """

    def test_propose_count_1_returns_singular_only(self, ar_state, tmp_path):
        """parallel_count=1 propose must set current_experiment (singular)
        and NOT set current_experiments (plural) — exact v1.5 behavior."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 1
        state["experiment_count"] = 0
        proposal_json = json.dumps({
            "description": "increase lr", "rationale": "r", "new_content": "print('new')\n",
        })
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=(proposal_json, {"total": 0})):
            result = node_propose(state)
        # Singular field set (v1.5 behavior).
        assert "current_experiment" in result
        assert result["current_experiment"]["iteration"] == 1
        # Plural field NOT set — single path doesn't touch it.
        assert "current_experiments" not in result

    def test_decide_count_1_uses_singular_fields(self, ar_state):
        """parallel_count=1 decide must read current_metric (singular)
        and current_experiment (singular) — exact v1.5 behavior."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state = dict(ar_state)
        state["parallel_count"] = 1
        state.update({
            "current_best": 0.5, "current_metric": 0.4,
            "metric_direction": "lower",
            "current_experiment": {"iteration": 1, "description": "good"},
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"), \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard"):
            result = node_decide(state)
        assert result["current_best"] == 0.4
        assert result["current_experiment"]["status"] == "keep"
        # Plural fields NOT set — single path doesn't touch them.
        assert "current_experiments" not in result
        assert "current_metrics" not in result


# ---------------------------------------------------------------------------
# node_propose — parallel path
# ---------------------------------------------------------------------------


class TestParallelPropose:
    """Test the parallel proposal path (parallel_count > 1)."""

    def test_generates_n_proposals_via_n_calls(self, ar_state, tmp_path):
        """parallel_count=3 must call _call_planner 3 times and return
        3 proposals in current_experiments."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["experiment_count"] = 0

        proposals = [
            json.dumps({"description": f"change {i}", "rationale": "r",
                        "new_content": f"# v{i}\n"})
            for i in range(3)
        ]
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        side_effects = [(p, {"total": 100 * i}) for i, p in enumerate(proposals)]
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=side_effects) as m:
            result = node_propose(state)

        assert m.call_count == 3
        assert "current_experiments" in result
        assert len(result["current_experiments"]) == 3
        # Iterations should be 1, 2, 3 (experiment_count=0 + 1 + i).
        iters = sorted(p["iteration"] for p in result["current_experiments"])
        assert iters == [1, 2, 3]
        # Singular field mirrors the first proposal (sorted by iteration).
        assert result["current_experiment"]["iteration"] == 1
        assert result["status"] == "running"

    def test_per_call_failure_records_placeholder(self, ar_state, tmp_path):
        """If one parallel call fails, the batch continues — the failed
        slot gets a placeholder proposal with status='failed'."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["experiment_count"] = 0

        # Call 1 succeeds, call 2 raises, call 3 succeeds.
        good = json.dumps({"description": "ok", "rationale": "r", "new_content": "x\n"})
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        side_effects = [(good, {"total": 10}), RuntimeError("LLM down"), (good, {"total": 10})]
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=side_effects):
            result = node_propose(state)

        proposals = result["current_experiments"]
        assert len(proposals) == 3
        # The failed one must have status="failed" + an LLM-call-failed description.
        failed = [p for p in proposals if p.get("status") == "failed"]
        assert len(failed) == 1
        assert "LLM call failed" in failed[0]["description"]
        # The other 2 must NOT be marked failed.
        ok = [p for p in proposals if p.get("status") != "failed"]
        assert len(ok) == 2
        # Status should still be "running" — not all failed.
        assert result["status"] == "running"

    def test_all_calls_fail_returns_status_failed(self, ar_state, tmp_path):
        """If ALL N parallel calls fail, propagate status='failed' (mirrors
        v1.5 single-call failure)."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 2
        state["experiment_count"] = 0

        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=RuntimeError("LLM down")), \
             patch("time.sleep"):  # skip retry backoff
            result = node_propose(state)

        assert result["status"] == "failed"
        assert "all 2 parallel" in result["error"]
        # Still returns the placeholder proposals so the loop can log them.
        assert len(result["current_experiments"]) == 2


# ---------------------------------------------------------------------------
# node_modify — parallel path
# ---------------------------------------------------------------------------


class TestParallelModify:
    """Test the parallel modify path (parallel_count > 1)."""

    def test_writes_each_proposal_to_temp_dir(self, ar_state, tmp_path):
        """Each proposal must be written to its own temp dir under
        {project_root}/.autoresearch/parallel/{i}/{target_file}."""
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [
            {"iteration": 1, "description": "a", "new_content": "print('a')\n"},
            {"iteration": 2, "description": "b", "new_content": "print('b')\n"},
            {"iteration": 3, "description": "c", "new_content": "print('c')\n"},
        ]

        result = node_modify(state)

        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        for i in range(3):
            target = parallel_dir / str(i) / "train.py"
            assert target.exists(), f"temp file {target} not created"
            assert target.read_text(encoding="utf-8") == f"print('{chr(ord('a') + i)}')\n"

        # The real target_file must NOT be touched in parallel mode.
        assert not (tmp_path / "train.py").exists()
        assert result["status"] == "running"

    def test_dedup_skips_proposal(self, ar_state, tmp_path):
        """A proposal whose new_content matches a prior experiment's hash
        must be marked status='failed' with error='duplicate'."""
        import hashlib
        from workflows.autoresearch_impl.nodes.modify import node_modify
        dup_content = "print('dup')\n"
        dup_hash = hashlib.md5(dup_content.encode()).hexdigest()
        state = dict(ar_state)
        state["parallel_count"] = 2
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [
            {"iteration": 1, "description": "fresh", "new_content": "print('fresh')\n"},
            {"iteration": 2, "description": "dup", "new_content": dup_content},
        ]
        state["experiment_history"] = [
            {"iteration": 0, "content_hash": dup_hash, "status": "discard"},
        ]

        result = node_modify(state)
        proposals = result["current_experiments"]
        # The dup proposal must be marked failed.
        assert proposals[1]["status"] == "failed"
        assert proposals[1]["error"] == "duplicate"
        # The fresh proposal must NOT be marked failed.
        assert proposals[0].get("status") != "failed"
        # And the dup's temp dir was never created.
        assert not (tmp_path / ".autoresearch" / "parallel" / "1" / "train.py").exists()

    def test_empty_new_content_marks_failed(self, ar_state, tmp_path):
        """A proposal with empty new_content must be marked status='failed'."""
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state["parallel_count"] = 2
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [
            {"iteration": 1, "description": "good", "new_content": "print('a')\n"},
            {"iteration": 2, "description": "empty", "new_content": ""},
        ]

        result = node_modify(state)
        proposals = result["current_experiments"]
        assert proposals[1]["status"] == "failed"
        assert proposals[1]["error"] == "empty new_content"


# ---------------------------------------------------------------------------
# node_run_experiment — parallel path
# ---------------------------------------------------------------------------


class TestParallelRunExperiment:
    """Test the parallel run_experiment path (parallel_count > 1)."""

    def test_runs_n_subprocesses_in_parallel(self, ar_state, tmp_path):
        """Each temp file must be run as a subprocess — the N outputs are
        stored in experiment_outputs (plural)."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        # Pre-create the temp dirs + files (as node_modify would have).
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        for i in range(3):
            (parallel_dir / str(i)).mkdir(parents=True)
            (parallel_dir / str(i) / "train.py").write_text(f"# v{i}\n", encoding="utf-8")

        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [
            {"iteration": i + 1} for i in range(3)
        ]

        # Mock _run_subprocess to return distinct outputs per call.
        outputs = [f"val_bpb: 0.4{i}\n" for i in range(3)]
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   side_effect=outputs) as m:
            result = node_run_experiment(state)

        assert m.call_count == 3
        assert "experiment_outputs" in result
        assert len(result["experiment_outputs"]) == 3
        # Outputs must be in the same order as the proposals (by index).
        for i, out in enumerate(result["experiment_outputs"]):
            assert f"0.4{i}" in out
        # Singular field mirrors the first output.
        assert result["experiment_output"] == result["experiment_outputs"][0]

    def test_missing_temp_file_returns_sentinel(self, ar_state, tmp_path):
        """If a temp file is missing (modify marked it failed), the run
        returns a 'skipped' sentinel for that slot — not an exception."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        # Only create temp dir 0 — proposal 1 was failed by modify.
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        (parallel_dir / "0").mkdir(parents=True)
        (parallel_dir / "0" / "train.py").write_text("# v0\n", encoding="utf-8")

        state = dict(ar_state)
        state["parallel_count"] = 2
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [
            {"iteration": 1}, {"iteration": 2, "status": "failed"},
        ]

        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.4\n") as m:
            result = node_run_experiment(state)

        # Only 1 actual subprocess call — the missing file short-circuits.
        assert m.call_count == 1
        outputs = result["experiment_outputs"]
        assert "skipped" in outputs[1].lower() or "file not found" in outputs[1].lower()
        # The other slot has the real output.
        assert "0.4" in outputs[0]


# ---------------------------------------------------------------------------
# node_evaluate — parallel path
# ---------------------------------------------------------------------------


class TestParallelEvaluate:
    """Test the parallel evaluate path (parallel_count > 1)."""

    def test_extracts_n_metrics_from_n_outputs(self, ar_state):
        """Each output yields its own metric; results stored in
        current_metrics (plural) + first mirrored to current_metric."""
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["metric_name"] = "val_bpb"
        state["experiment_outputs"] = [
            "val_bpb: 0.45\n",
            "val_bpb: 0.40\n",
            "val_bpb: 0.50\n",
        ]

        result = node_evaluate(state)
        assert "current_metrics" in result
        assert result["current_metrics"] == [0.45, 0.40, 0.50]
        # Singular field mirrors the first metric.
        assert result["current_metric"] == 0.45

    def test_missing_metric_yields_zero(self, ar_state):
        """An output with no extractable metric yields 0.0 for that slot."""
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state["parallel_count"] = 2
        state["metric_name"] = "val_bpb"
        state["experiment_outputs"] = [
            "val_bpb: 0.45\n",
            "no metric here\n",
        ]

        result = node_evaluate(state)
        assert result["current_metrics"][0] == 0.45
        assert result["current_metrics"][1] == 0.0


# ---------------------------------------------------------------------------
# node_decide — parallel path
# ---------------------------------------------------------------------------


class TestParallelDecide:
    """Test the parallel decide path (parallel_count > 1)."""

    def _state_with_3_experiments(self, ar_state, tmp_path, metrics):
        """Build a state with 3 proposals + temp files + metrics for decide."""
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        proposals = []
        for i in range(3):
            exp_dir = parallel_dir / str(i)
            exp_dir.mkdir(parents=True, exist_ok=True)
            (exp_dir / "train.py").write_text(f"# version {i}\n", encoding="utf-8")
            proposals.append({
                "iteration": i + 1,
                "description": f"change {i}",
                "new_content": f"# version {i}\n",
                "content_hash": f"hash{i}",
            })
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["metric_direction"] = "lower"
        state["current_best"] = 0.5
        state["current_experiments"] = proposals
        state["current_metrics"] = metrics
        return state, parallel_dir

    def test_picks_best_and_copies_winner_to_real_target(self, ar_state, tmp_path):
        """The best experiment's content must be copied to the real
        target_file and committed. Losers are annotated 'discard'."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        # Metrics: 0.45, 0.40, 0.50 — best is index 1 (0.40, lowest).
        state, parallel_dir = self._state_with_3_experiments(ar_state, tmp_path,
                                                              [0.45, 0.40, 0.50])

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234") as mock_commit:
            result = node_decide(state)

        # The winner's content must be in the real target_file.
        assert (tmp_path / "train.py").read_text(encoding="utf-8") == "# version 1\n"
        # The commit must have happened with the winner's description.
        assert mock_commit.called
        commit_msg = mock_commit.call_args[0][0]
        assert "change 1" in commit_msg

        # The winner is annotated 'keep'; losers 'discard'.
        proposals = result["current_experiments"]
        statuses = [p["status"] for p in proposals]
        assert statuses == ["discard", "keep", "discard"]
        # current_best updated to the winner's metric.
        assert result["current_best"] == 0.40
        # Temp dir cleaned up.
        assert not parallel_dir.exists()

    def test_no_improvement_discards_all(self, ar_state, tmp_path):
        """When no experiment improves on current_best, all are discarded
        and current_best is unchanged."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        # All metrics >= current_best (0.5) → no improvement (direction=lower).
        state, parallel_dir = self._state_with_3_experiments(ar_state, tmp_path,
                                                              [0.6, 0.55, 0.7])

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit") as mock_commit:
            result = node_decide(state)

        # No commit attempted.
        assert not mock_commit.called
        # All discarded.
        statuses = [p["status"] for p in result["current_experiments"]]
        assert statuses == ["discard", "discard", "discard"]
        # current_best unchanged.
        assert result["current_best"] == 0.5
        # Temp dir cleaned up.
        assert not parallel_dir.exists()

    def test_skips_failed_proposals(self, ar_state, tmp_path):
        """Proposals marked status='failed' by modify must be skipped —
        only the non-failed ones are eligible to win."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state, parallel_dir = self._state_with_3_experiments(ar_state, tmp_path,
                                                              [0.45, 0.40, 0.50])
        # Mark proposal 1 (the would-be winner) as failed.
        state["current_experiments"][1]["status"] = "failed"

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"):
            result = node_decide(state)

        # Proposal 0 (metric 0.45) is now the best non-failed — should win.
        proposals = result["current_experiments"]
        assert proposals[0]["status"] == "keep"
        assert proposals[1]["status"] == "discard"  # was failed
        assert proposals[2]["status"] == "discard"
        assert result["current_best"] == 0.45

    def test_temp_dir_cleaned_on_no_improvement(self, ar_state, tmp_path):
        """The temp dir must be cleaned up even on the no-improvement path."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state, parallel_dir = self._state_with_3_experiments(ar_state, tmp_path,
                                                              [0.6, 0.55, 0.7])
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit"):
            node_decide(state)
        assert not parallel_dir.exists(), "temp dir leaked on no-improvement path"

    def test_commit_failure_discards_winner_too(self, ar_state, tmp_path):
        """If git commit fails (empty SHA), the winner is also annotated
        'discard' and current_best is NOT updated (mirrors v1.5 P1-1)."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state, parallel_dir = self._state_with_3_experiments(ar_state, tmp_path,
                                                              [0.45, 0.40, 0.50])

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value=""):  # empty SHA = commit failed
            result = node_decide(state)

        # All discarded (including the would-be winner).
        statuses = [p["status"] for p in result["current_experiments"]]
        assert statuses == ["discard", "discard", "discard"]
        # current_best NOT updated.
        assert result["current_best"] == 0.5
        # Temp dir still cleaned up.
        assert not parallel_dir.exists()


# ---------------------------------------------------------------------------
# node_log — parallel path
# ---------------------------------------------------------------------------


class TestParallelLog:
    """Test the parallel log path (parallel_count > 1)."""

    def test_appends_n_rows_to_ledger(self, ar_state, tmp_path):
        """N experiments must produce N ledger rows."""
        from workflows.autoresearch_impl.nodes.log import node_log
        results_path = tmp_path / "results.tsv"
        results_path.write_text("iteration\tcommit\tmetric\tstatus\tdescription\n",
                                encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["experiment_history"] = []
        state["current_experiments"] = [
            {"iteration": 1, "description": "a", "metric": 0.45,
             "status": "discard", "commit": "", "content_hash": "h1"},
            {"iteration": 2, "description": "b", "metric": 0.40,
             "status": "keep", "commit": "abc1234", "content_hash": "h2"},
            {"iteration": 3, "description": "c", "metric": 0.50,
             "status": "discard", "commit": "", "content_hash": "h3"},
        ]

        result = node_log(state)

        content = results_path.read_text(encoding="utf-8")
        # 3 new rows appended.
        rows = [l for l in content.splitlines() if l and not l.startswith("iteration")]
        assert len(rows) == 3
        # Row 2 (the keeper) must have the commit SHA.
        assert any("abc1234" in r and "keep" in r for r in rows)

        # experiment_count must increment by N.
        assert result["experiment_count"] == 3
        # experiment_history must have N new entries.
        assert len(result["experiment_history"]) == 3
        # Plural field cleared for next iteration.
        assert result["current_experiments"] == []
        # Singular field also cleared (backward compat).
        assert result["current_experiment"] == {}

    def test_history_cap_applies_to_parallel_too(self, ar_state, tmp_path):
        """The 100-entry history cap must apply in parallel mode too."""
        from workflows.autoresearch_impl.nodes.log import node_log
        results_path = tmp_path / "results.tsv"
        results_path.write_text("header\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        # Pre-fill 99 entries — appending 3 more should cap to 100.
        state["experiment_history"] = [
            {"iteration": i, "description": f"old{i}", "metric": 0.1,
             "status": "discard", "commit": ""}
            for i in range(99)
        ]
        state["current_experiments"] = [
            {"iteration": 100, "description": "a", "metric": 0.45,
             "status": "discard", "commit": "", "content_hash": "h1"},
            {"iteration": 101, "description": "b", "metric": 0.40,
             "status": "keep", "commit": "abc", "content_hash": "h2"},
            {"iteration": 102, "description": "c", "metric": 0.50,
             "status": "discard", "commit": "", "content_hash": "h3"},
        ]

        result = node_log(state)
        assert len(result["experiment_history"]) == 100
        # Most-recent 3 (the just-appended entries) must be present.
        iters = [h["iteration"] for h in result["experiment_history"]]
        assert 100 in iters and 101 in iters and 102 in iters


# ---------------------------------------------------------------------------
# End-to-end parallel iteration
# ---------------------------------------------------------------------------


class TestParallelEndToEnd:
    """Exercise the full propose → modify → run → evaluate → decide → log
    chain in parallel mode (all nodes real, _call_planner + _run_subprocess
    + _git_commit mocked)."""

    def test_full_parallel_iteration(self, ar_state, tmp_path):
        """A full parallel iteration with parallel_count=3 must:
        - call _call_planner 3×
        - write 3 temp files
        - run 3 subprocesses
        - extract 3 metrics
        - pick the best + commit it
        - log 3 rows to results.tsv
        - leave no temp dir behind
        """
        from workflows.autoresearch_impl.nodes.propose import node_propose
        from workflows.autoresearch_impl.nodes.modify import node_modify
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        from workflows.autoresearch_impl.nodes.decide import node_decide
        from workflows.autoresearch_impl.nodes.log import node_log

        # Seed the project: write the baseline train.py.
        (tmp_path / "train.py").write_text("print('baseline')\n", encoding="utf-8")
        results_path = tmp_path / "results.tsv"
        results_path.write_text("iteration\tcommit\tmetric\tstatus\tdescription\n",
                                encoding="utf-8")

        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["current_best"] = 0.5
        state["metric_direction"] = "lower"
        state["experiment_history"] = []

        # 1. Propose — 3 different proposals. Each proposal's new_content
        # is a Python script that prints val_bpb: <value> so evaluate can
        # extract the metric.
        proposals = [
            json.dumps({"description": f"change {i}", "rationale": "r",
                        "new_content": f"print('v{i}'); print('val_bpb: {0.45 + i * 0.05}')\n"})
            for i in range(3)
        ]
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        side_effects = [(p, {"total": 0}) for p in proposals]
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=side_effects):
            state.update(node_propose(state))
        assert len(state["current_experiments"]) == 3

        # 2. Modify — writes 3 temp files.
        state.update(node_modify(state))
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        assert (parallel_dir / "0" / "train.py").exists()
        assert (parallel_dir / "1" / "train.py").exists()
        assert (parallel_dir / "2" / "train.py").exists()

        # 3. Run — 3 subprocesses. The temp scripts print val_bpb=N.
        state.update(node_run_experiment(state))
        assert len(state["experiment_outputs"]) == 3

        # 4. Evaluate — 3 metrics.
        state.update(node_evaluate(state))
        assert len(state["current_metrics"]) == 3

        # 5. Decide — pick best (lowest val_bpb = index 0 = 0.45).
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"):
            state.update(node_decide(state))

        # Winner's content copied to real target_file.
        assert "v0" in (tmp_path / "train.py").read_text(encoding="utf-8")
        # current_best updated to the winning metric.
        assert state["current_best"] == 0.45
        # Temp dir cleaned up.
        assert not parallel_dir.exists()

        # 6. Log — 3 rows in results.tsv.
        state.update(node_log(state))
        rows = [l for l in results_path.read_text(encoding="utf-8").splitlines()
                if l and not l.startswith("iteration")]
        assert len(rows) == 3
        # experiment_count incremented by 3.
        assert state["experiment_count"] == 3
        # Plural field cleared for next iteration.
        assert state["current_experiments"] == []


# ===========================================================================
# [v1.9 C1] Atomic batched parallel ledger write (mimo C3, qwen P2-5)
# ===========================================================================


class TestLedgerAtomicBatchedWrite:
    """[v1.9 C1] Parallel path batches all N rows into a SINGLE open("a")
    call (was: N separate calls). The single path adds f.flush() +
    os.fsync(f.fileno()) before close.
    """

    def test_parallel_log_writes_all_rows_in_single_call(self, ar_state, tmp_path):
        """Patch builtins.open to track call count — verify the parallel path
        opens the file ONCE (not N times)."""
        from workflows.autoresearch_impl.nodes import log as log_mod
        results_path = tmp_path / "results.tsv"
        results_path.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash\n",
            encoding="utf-8",
        )
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["experiment_history"] = []
        state["current_experiments"] = [
            {"iteration": 1, "description": "a", "metric": 0.45,
             "status": "discard", "commit": "", "content_hash": "h1"},
            {"iteration": 2, "description": "b", "metric": 0.40,
             "status": "keep", "commit": "abc1234", "content_hash": "h2"},
            {"iteration": 3, "description": "c", "metric": 0.50,
             "status": "discard", "commit": "", "content_hash": "h3"},
        ]

        # Track open() calls in append mode ("a").
        original_open = __builtins__.open if hasattr(__builtins__, "open") else open
        open_calls = []

        def tracking_open(path, mode="r", *args, **kwargs):
            if "a" in mode:
                open_calls.append((str(path), mode))
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=tracking_open):
            log_mod.node_log(state)

        # Filter to only the results.tsv appends (fsync opens the fd, not the file).
        tsv_appends = [c for c in open_calls if "results.tsv" in c[0]]
        assert len(tsv_appends) == 1, (
            f"parallel path should open results.tsv ONCE in append mode, "
            f"got {len(tsv_appends)} calls"
        )
