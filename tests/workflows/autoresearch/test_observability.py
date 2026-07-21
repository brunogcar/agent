"""tests/workflows/autoresearch/test_observability.py

[v1.8] Tests for the observability commit (3 features):

Coverage:
  N5  — Output logging: full stdout+stderr written to
        `{project_root}/.autoresearch/logs/{iteration}.log` BEFORE truncation (single path)
        and `{iteration}_{i}.log` (parallel path, one per experiment).
        [v1.9-V2 correction #1] Log dir relocated from `logs/autoresearch/` (at
        project root level) to `{project_root}/.autoresearch/logs/` (mirrors
        the `.understand` project-scoped pattern).
  N6  — Cost/token tracking: `_call_planner` returns `(response, usage)`
        tuple; `node_propose` captures `usage.get("total", 0)` on the
        proposal as `tokens`; `node_log._build_history_entry` persists
        `tokens` in `experiment_history` entries.
  N10 — Output truncation fix: `node_run_experiment` extracts the metric
        from the FULL output BEFORE truncating to 50KB and stores it in
        `pre_extracted_metric`. `node_evaluate` reads this first (skipping
        re-extraction from the truncated output), preventing false negatives
        when the metric was printed early and the script produced lots of
        output after (pushing the metric out of the 50KB tail).

[v1.8 tests] New file — all 3 observability features were previously
untested in isolation. The v1.7 baseline tests verified behavior via
mocks that returned strings (not the new tuple shape) — those tests were
updated in-place for the v1.8 N6 `_call_planner` signature change. This
file covers the NEW behavior that didn't exist before v1.8.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# N5: Output logging — full stdout+stderr to per-iteration log file
# ---------------------------------------------------------------------------


class TestOutputLogging:
    """[v1.8 N5] Full output written to {project_root}/.autoresearch/logs/{iteration}.log
    BEFORE truncation. Operators can inspect the full output for debugging.
    [v1.9-V2 correction #1] Log dir relocated from `logs/autoresearch/` (at
    project root level) to `{project_root}/.autoresearch/logs/`.
    """

    def test_single_path_writes_full_output_to_log(self, ar_state, tmp_path):
        """Single-mode path: full output written to {iteration}.log."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        results_path = tmp_path / "results.tsv"
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = str(results_path)
        state["project_root"] = str(tmp_path)
        state["experiment_count"] = 7  # → iteration 8
        # 60KB output — bigger than the 50KB truncation threshold.
        full_output = "val_bpb: 0.42\n" + ("DEBUG: training step\n" * 5000)
        assert len(full_output) > 50_000  # sanity
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value=full_output):
            node_run_experiment(state)

        # [v1.9-V2 correction #1] Log dir relocated from logs/autoresearch/
        # (at project root level) to {project_root}/.autoresearch/logs/
        log_file = tmp_path / ".autoresearch" / "logs" / "8.log"
        assert log_file.exists(), f"log file {log_file} not created"
        logged = log_file.read_text(encoding="utf-8")
        # The log file contains the FULL output — not truncated.
        assert len(logged) == len(full_output)
        assert logged == full_output
        # The metric (printed early) is preserved in the log even though
        # it would be lost in the truncated state copy.
        assert "val_bpb: 0.42" in logged

    def test_single_path_log_file_uses_iteration_from_experiment_count(self, ar_state, tmp_path):
        """The log filename is {experiment_count + 1}.log — matches the
        iteration number node_propose stamps on the proposal."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        results_path = tmp_path / "results.tsv"
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = str(results_path)
        state["project_root"] = str(tmp_path)
        state["experiment_count"] = 3
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.5\n"):
            node_run_experiment(state)
        # experiment_count=3 → iteration=4 → log filename "4.log".
        # [v1.9-V2 correction #1] Log dir relocated to {project_root}/.autoresearch/logs/
        assert (tmp_path / ".autoresearch" / "logs" / "4.log").exists()

    def test_parallel_path_writes_one_log_per_experiment(self, ar_state, tmp_path):
        """Parallel path: writes N log files named {iteration}_{i}.log.

        [v1.9 fix] Deterministic output mapping — the side_effect inspects the
        target_path arg (which encodes the slot index `parallel/{i}/`) and
        returns the output for THAT slot. This avoids the pre-existing thread-
        scheduling flakiness where `as_completed` could yield futures in a
        different order than submission, causing `results[idx]` to get the
        wrong output from a naive `side_effect=outputs` list.
        """
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        results_path = tmp_path / "results.tsv"
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        n = 3
        for i in range(n):
            exp_dir = parallel_dir / str(i)
            exp_dir.mkdir(parents=True)
            (exp_dir / "train.py").write_text(f"# v{i}\n", encoding="utf-8")
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = str(results_path)
        state["project_root"] = str(tmp_path)
        state["parallel_count"] = n
        state["experiment_count"] = 0  # → iteration 1
        state["target_file"] = "train.py"
        state["current_experiments"] = [{"iteration": i + 1} for i in range(n)]

        # Map slot index → output. The side_effect function parses the
        # target_path arg (e.g. ".../.autoresearch/parallel/1/train.py") to
        # extract the slot index, so the right output goes to the right slot
        # regardless of thread completion order.
        outputs = {i: f"val_bpb: 0.4{i}\n" for i in range(n)}

        def _fake_run(target_path, project_root, time_budget):
            # target_path looks like ".../.autoresearch/parallel/{i}/train.py"
            # Extract the slot index from the path.
            from pathlib import Path as _P
            slot = int(_P(target_path).parent.name)
            return outputs[slot]

        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   side_effect=_fake_run):
            node_run_experiment(state)

        # [v1.9-V2 correction #1] Log dir relocated to {project_root}/.autoresearch/logs/
        log_dir = tmp_path / ".autoresearch" / "logs"
        # One log file per experiment: 1_0.log, 1_1.log, 1_2.log
        for i in range(n):
            log_file = log_dir / f"1_{i}.log"
            assert log_file.exists(), f"log file {log_file} not created"
            assert log_file.read_text(encoding="utf-8") == outputs[i]

    def test_log_write_failure_is_non_fatal(self, ar_state, tmp_path):
        """A disk-write error on the log file must NOT halt the experiment
        loop — node_run_experiment should still return its normal result."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        results_path = tmp_path / "results.tsv"
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = str(results_path)
        state["project_root"] = str(tmp_path)
        state["experiment_count"] = 0
        # Force the log file write to fail by patching Path.write_text.
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")), \
             patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.42\n"):
            result = node_run_experiment(state)
        # The node still returned normally — the log failure was swallowed.
        assert result["status"] == "running"
        assert result["experiment_output"] == "val_bpb: 0.42\n"
        assert result["pre_extracted_metric"] == 0.42
        # And the log file was NOT created (write failed).
        # [v1.9-V2 correction #1] Log dir relocated to {project_root}/.autoresearch/logs/
        assert not (tmp_path / ".autoresearch" / "logs" / "1.log").exists()

    def test_no_log_file_when_results_path_empty(self, ar_state):
        """When results_path is empty, no log file is written (non-fatal
        no-op). The node still returns its normal result."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state["status"] = "running"
        state["results_path"] = ""  # empty — should skip logging
        state["experiment_count"] = 0
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value="val_bpb: 0.42\n"):
            result = node_run_experiment(state)
        assert result["status"] == "running"
        assert result["experiment_output"] == "val_bpb: 0.42\n"


# ---------------------------------------------------------------------------
# N6: Cost/token tracking — _call_planner tuple + proposal.tokens + history
# ---------------------------------------------------------------------------


class TestTokenTracking:
    """[v1.8 N6] _call_planner returns (response, usage); node_propose
    captures usage['total'] on the proposal as `tokens`; node_log persists
    `tokens` in experiment_history entries.
    """

    def test_call_planner_returns_response_and_usage_tuple(self):
        """_call_planner returns (response, usage) — not just response."""
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        usage_dict = {"total": 1234, "prompt": 800, "completion": 434}
        with patch("tools.agent.agent",
                   return_value={"status": "success", "response": "ok",
                                 "usage": usage_dict}):
            result = _call_planner("sys", "user", tid="t1")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "ok"
        assert result[1] == usage_dict

    def test_node_propose_captures_tokens_on_proposal(self, ar_state, tmp_path):
        """node_propose stores usage['total'] on the proposal as 'tokens'."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["experiment_count"] = 0
        proposal_json = json.dumps({
            "description": "test", "rationale": "r", "new_content": "print('new')\n",
        })
        # _call_planner returns (response, usage) with total=2345 tokens.
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=(proposal_json, {"total": 2345, "prompt": 1500})):
            result = node_propose(state)
        ce = result["current_experiment"]
        assert ce["tokens"] == 2345  # total token count captured

    def test_node_propose_parallel_path_captures_tokens_per_proposal(self, ar_state, tmp_path):
        """Parallel path: each proposal gets its own tokens count from
        its own _call_planner call."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["experiment_count"] = 0
        # Each call returns a different token count.
        proposals_with_usage = [
            (json.dumps({"description": f"a{i}", "rationale": "r", "new_content": f"v{i}\n"}),
             {"total": 100 * (i + 1)})
            for i in range(3)
        ]
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=proposals_with_usage):
            result = node_propose(state)
        tokens = sorted(p["tokens"] for p in result["current_experiments"])
        assert tokens == [100, 200, 300]

    def test_node_propose_defaults_tokens_to_zero_when_usage_missing(self, ar_state, tmp_path):
        """When _call_planner returns usage={} (older subagent / mock),
        proposal['tokens'] defaults to 0."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["experiment_count"] = 0
        proposal_json = json.dumps({
            "description": "test", "rationale": "r", "new_content": "print('new')\n",
        })
        # usage is {} — no 'total' key.
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=(proposal_json, {})):
            result = node_propose(state)
        assert result["current_experiment"]["tokens"] == 0

    def test_build_history_entry_includes_tokens(self):
        """_build_history_entry persists the proposal's `tokens` field."""
        from workflows.autoresearch_impl.nodes.log import _build_history_entry
        proposal = {
            "iteration": 5,
            "description": "test",
            "metric": 0.42,
            "status": "keep",
            "commit": "abc123",
            "content_hash": "deadbeef",
            "tokens": 4321,
        }
        entry = _build_history_entry(proposal, 0.0)
        assert entry["tokens"] == 4321

    def test_build_history_entry_defaults_tokens_to_zero(self):
        """_build_history_entry defaults `tokens` to 0 when the proposal
        didn't carry one (e.g. failed-proposal placeholders)."""
        from workflows.autoresearch_impl.nodes.log import _build_history_entry
        proposal = {
            "iteration": 5,
            "description": "(LLM call failed)",
            "status": "failed",
            # no 'tokens' key — should default to 0
        }
        entry = _build_history_entry(proposal, 0.0)
        assert entry["tokens"] == 0

    def test_node_log_persists_tokens_in_history(self, ar_state, tmp_path):
        """End-to-end: node_propose sets tokens → node_decide annotates →
        node_log persists tokens in experiment_history."""
        from workflows.autoresearch_impl.nodes.log import node_log
        results_path = tmp_path / "results.tsv"
        results_path.write_text("iteration\tcommit\tmetric\tstatus\tdescription\n",
                                encoding="utf-8")
        state = dict(ar_state)
        state["results_path"] = str(results_path)
        state["experiment_count"] = 0
        state["experiment_history"] = []
        # current_experiment annotated by decide, carrying tokens from propose.
        state["current_experiment"] = {
            "iteration": 1, "description": "lr=1e-4", "metric": 0.42,
            "status": "keep", "commit": "abc1234", "content_hash": "h1",
            "tokens": 5555,
        }
        result = node_log(state)
        assert len(result["experiment_history"]) == 1
        assert result["experiment_history"][0]["tokens"] == 5555


# ---------------------------------------------------------------------------
# N10: Output truncation improvement — pre-extract metric BEFORE truncation
# ---------------------------------------------------------------------------


class TestPreExtractedMetric:
    """[v1.8 N10] node_run_experiment extracts the metric from the FULL
    output BEFORE truncating to 50KB. node_evaluate reads this first,
    preventing false negatives when the metric was printed early.
    """

    def test_metric_pre_extracted_before_truncation(self, ar_state):
        """When the metric is printed early and the script produces lots
        of output after, the metric MUST still be pre-extracted from the
        FULL output (before truncation)."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state["status"] = "running"
        state["metric_name"] = "val_bpb"
        # Metric printed at the START; 60KB of noise after (would push the
        # metric out of the 50KB tail).
        big = "val_bpb: 0.37\n" + ("X" * 60_000)
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value=big):
            result = node_run_experiment(state)
        # Output truncated — the metric is NOT in the truncated tail.
        assert "val_bpb: 0.37" not in result["experiment_output"]
        # But pre_extracted_metric was extracted from the FULL output.
        assert result["pre_extracted_metric"] == 0.37

    def test_pre_extracted_metric_is_none_when_metric_not_in_output(self, ar_state):
        """When the metric is NOT in the full output (e.g. script crashed
        before printing it), pre_extracted_metric is None."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        state = dict(ar_state)
        state["status"] = "running"
        state["metric_name"] = "val_bpb"
        # Output without the metric.
        output = "training...\nerror: something went wrong\ntraceback...\n"
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value=output):
            result = node_run_experiment(state)
        assert result["pre_extracted_metric"] is None

    def test_evaluate_uses_pre_extracted_metric_when_set(self, ar_state):
        """node_evaluate reads pre_extracted_metric FIRST — when set, it
        trusts it and skips re-extracting from the (truncated) output."""
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state["metric_name"] = "val_bpb"
        state["status"] = "running"
        # The truncated output does NOT contain the metric (was printed
        # early and pushed out of the 50KB tail).
        state["experiment_output"] = "X" * 1000  # no metric in truncated output
        # But pre_extracted_metric was captured from the FULL output.
        state["pre_extracted_metric"] = 0.37
        result = node_evaluate(state)
        # evaluate trusted the pre-extracted metric — no false negative.
        assert result["current_metric"] == 0.37
        assert result["status"] == "running"
        assert result["error"] == ""

    def test_evaluate_falls_back_when_pre_extracted_is_none(self, ar_state):
        """When pre_extracted_metric is None (no metric in full output),
        evaluate falls back to extracting from the (truncated) output."""
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state["metric_name"] = "val_bpb"
        state["status"] = "running"
        # The truncated output DOES contain the metric (printed at the end).
        state["experiment_output"] = "training...\nval_bpb: 0.42\n"
        # pre_extracted_metric is None — metric wasn't in the full output
        # (impossible scenario in practice, but tests the fallback path).
        # Actually, if metric is in the truncated output, it must have been
        # in the full output too. So a more realistic test: pre_extracted
        # is None and the truncated output also doesn't have the metric.
        state["pre_extracted_metric"] = None
        state["experiment_output"] = "no metric here\n"
        result = node_evaluate(state)
        # Both pre_extracted and output extraction failed → status="failed".
        assert result["current_metric"] == 0.0
        assert result["status"] == "failed"
        assert "not found" in result["error"]

    def test_evaluate_prevents_false_negative_truncation_scenario(self, ar_state):
        """Integration: a script prints the metric EARLY then produces lots
        of output. Without N10, the truncated output has no metric and
        evaluate would return status='failed' (false negative). With N10,
        the pre-extracted metric is used and evaluate returns the correct
        metric."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        # Simulate: metric at start + 60KB noise → truncated output has no metric.
        big = "val_bpb: 0.37\n" + ("X" * 60_000)
        state = dict(ar_state)
        state["status"] = "running"
        state["metric_name"] = "val_bpb"
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   return_value=big):
            run_result = node_run_experiment(state)
        # Pre-extracted metric is set correctly.
        assert run_result["pre_extracted_metric"] == 0.37
        # The truncated output has NO metric (would be a false negative pre-N10).
        assert "val_bpb" not in run_result["experiment_output"]
        # Wire the run_experiment result into the evaluate state.
        eval_state = dict(state)
        eval_state.update(run_result)
        eval_result = node_evaluate(eval_state)
        # evaluate trusted the pre-extracted metric — no false negative.
        assert eval_result["current_metric"] == 0.37
        assert eval_result["status"] == "running"

    def test_pre_extracted_metric_none_does_not_short_circuit_evaluate(self, ar_state):
        """When pre_extracted_metric is None (no metric found in full
        output), evaluate must NOT short-circuit — it must fall through to
        the extraction-from-output path. This is important because the
        full output might genuinely have no metric, but the truncated tail
        might (impossible in practice, but the code path must be safe)."""
        from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
        state = dict(ar_state)
        state["metric_name"] = "val_bpb"
        state["status"] = "running"
        state["experiment_output"] = "val_bpb: 0.99\n"  # metric in output
        state["pre_extracted_metric"] = None  # but pre-extract said None
        result = node_evaluate(state)
        # Fell through to extraction-from-output — got the metric from there.
        assert result["current_metric"] == 0.99
        assert result["status"] == "running"

    def test_parallel_path_clears_pre_extracted_metric(self, ar_state, tmp_path):
        """[v1.8 N10] Parallel path sets pre_extracted_metric=None explicitly
        — prevents a stale value from a prior single-mode iteration from
        leaking into the next single-mode evaluate."""
        from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        for i in range(2):
            (parallel_dir / str(i)).mkdir(parents=True)
            (parallel_dir / str(i) / "train.py").write_text(f"# v{i}\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 2
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["current_experiments"] = [{"iteration": 1}, {"iteration": 2}]
        with patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess",
                   side_effect=["val_bpb: 0.4\n", "val_bpb: 0.5\n"]):
            result = node_run_experiment(state)
        assert result["pre_extracted_metric"] is None
