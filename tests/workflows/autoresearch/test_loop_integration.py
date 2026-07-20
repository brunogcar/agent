"""tests/workflows/autoresearch/test_loop_integration.py

[v1.0] Integration tests that verify the autoresearch loop actually runs
end-to-end (with mocked LLM + subprocess + git). These tests catch state-
passing bugs that the pure-graph-topology tests in test_graph.py can't.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from workflows.autoresearch import build_autoresearch_graph
from workflows.autoresearch_impl.state import _default_state


@pytest.fixture
def ar_state(tmp_path):
    """A default autoresearch state pointing at a temp project dir."""
    return _default_state(
        goal="minimize val_bpb",
        trace_id="test-ar-loop",
        project_root=str(tmp_path),
        target_file="train.py",
        metric_name="val_bpb",
        metric_direction="lower",
        time_budget=10,
        branch="autoresearch/test",
        results_path=str(tmp_path / "results.tsv"),
    )


class TestAutoresearchLoop:
    """End-to-end tests of the experiment loop with all I/O mocked."""

    def test_loop_runs_one_iteration_then_recurses(self, ar_state, tmp_path):
        """The loop must execute setup → propose → modify → run_experiment →
        evaluate → decide → log → propose (loop) in the correct order.

        [v1.3 P0-1] Graph order changed from `evaluate → log → decide` to
        `evaluate → decide → log` — `decide` now annotates `current_experiment`
        BEFORE `log` reads it (was: log read pre-decide status, so the ledger
        always said "discard").

        We mock every node to return trivial state and let the loop hit
        LangGraph's recursion_limit (set low) — that proves the loop is wired
        correctly. The GraphRecursionError is the EXPECTED exit condition
        (the loop is supposed to run indefinitely).
        """
        # Write a fake train.py so modify's atomic write succeeds
        (tmp_path / "train.py").write_text("print('hello')\n", encoding="utf-8")

        call_order = []

        def _make_node(name, return_value):
            def _node(state):
                call_order.append(name)
                return dict(return_value)
            return _node

        # IMPORTANT: patches must be active BEFORE build_autoresearch_graph()
        # is called, because the graph captures references to the node functions
        # at build time. Patching the module attribute after build doesn't
        # affect what the graph invokes.
        #
        # We patch at the graph module level (workflows.autoresearch_impl.graph)
        # because graph.py does `from .nodes.setup import node_setup` — that
        # creates a binding in graph.py's namespace. Patching the original
        # module (workflows.autoresearch_impl.nodes.setup.node_setup) does NOT
        # affect the binding in graph.py.
        with patch("workflows.autoresearch_impl.graph.node_setup",
                   side_effect=_make_node("setup", {
                       "status": "running",
                       "experiment_count": 0,
                       "current_best": 0.5,
                       "baseline_metric": 0.5,
                       "branch": "autoresearch/test",
                       "results_path": ar_state["results_path"],
                   })), \
             patch("workflows.autoresearch_impl.graph.node_propose",
                   side_effect=_make_node("propose", {
                       "current_experiment": {
                           "iteration": 1,
                           "description": "test proposal",
                           "new_content": "print('hello')\n",
                       },
                   })), \
             patch("workflows.autoresearch_impl.graph.node_modify",
                   side_effect=_make_node("modify", {"status": "running"})), \
             patch("workflows.autoresearch_impl.graph.node_run_experiment",
                   side_effect=_make_node("run_experiment", {
                       "experiment_output": "val_bpb: 0.45\n",
                   })), \
             patch("workflows.autoresearch_impl.graph.node_evaluate",
                   side_effect=_make_node("evaluate", {
                       "current_metric": 0.45,
                       "status": "running",
                   })), \
             patch("workflows.autoresearch_impl.graph.node_decide",
                   side_effect=_make_node("decide", {
                       "current_best": 0.45,
                       "current_experiment": {
                           "iteration": 1, "status": "keep", "commit": "abc1234",
                           "metric": 0.45, "description": "test proposal",
                       },
                   })), \
             patch("workflows.autoresearch_impl.graph.node_log",
                   side_effect=_make_node("log", {
                       "experiment_count": 1,
                       "experiment_history": [{"iteration": 1, "status": "keep"}],
                       "current_experiment": {},
                   })):
            # Build the graph INSIDE the patch context so the compiled graph
            # captures the mocked node functions.
            graph = build_autoresearch_graph()
            # recursion_limit=12 → ~2 iterations (7 nodes per iter: setup+6)
            with pytest.raises(Exception) as exc_info:
                graph.invoke(ar_state, config={"recursion_limit": 12})
            # The expected exception is GraphRecursionError
            assert "Recursion" in type(exc_info.value).__name__ or \
                   "recursion" in str(exc_info.value).lower(), (
                f"expected GraphRecursionError, got {type(exc_info.value).__name__}: {exc_info.value}"
            )

        # Verify the call order: setup must come first, then propose → modify
        # → run_experiment → evaluate → decide → log → propose (loop)
        # [v1.3 P0-1] Order changed: was evaluate → log → decide; now evaluate → decide → log
        assert call_order[0] == "setup", (
            f"setup must be called first, got: {call_order[:5]}"
        )
        # The first iteration (after setup) must follow the expected order
        post_setup = call_order[1:7]
        assert post_setup == ["propose", "modify", "run_experiment",
                              "evaluate", "decide", "log"], (
            f"first iteration must follow the expected order, got: {post_setup}"
        )
        # The loop must come back to propose (now via log → propose edge)
        assert "propose" in call_order[7:], (
            f"loop must come back to propose after log, got: {call_order[7:]}"
        )

    def test_decide_discard_does_not_update_current_best(self, ar_state, tmp_path):
        """When current_metric is worse than current_best, decide must NOT
        update current_best (it should stay at the prior best).

        We test this by calling node_decide directly — it's a unit test of
        the decision logic, not a full loop integration test.
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide

        # current_metric=0.6 > current_best=0.5 with direction=lower → worse
        state = dict(ar_state)
        state.update({
            "current_best": 0.5,
            "current_metric": 0.6,
            "metric_direction": "lower",
            "current_experiment": {
                "iteration": 1,
                "description": "bad change",
                "metric": 0.6,
            },
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard") as mock_reset:
            mock_reset.return_value = True
            result = node_decide(state)

        assert result["current_best"] == 0.5, (
            "current_best must NOT update when the experiment is worse"
        )
        assert result["current_experiment"]["status"] == "discard"
        mock_reset.assert_called_once()

    def test_decide_keep_updates_current_best(self, ar_state, tmp_path):
        """When current_metric is better than current_best, decide must
        update current_best AND commit the change.
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide

        # current_metric=0.4 < current_best=0.5 with direction=lower → better
        state = dict(ar_state)
        state.update({
            "current_best": 0.5,
            "current_metric": 0.4,
            "metric_direction": "lower",
            "current_experiment": {
                "iteration": 1,
                "description": "good change",
                "metric": 0.4,
            },
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit") as mock_commit:
            mock_commit.return_value = "abc1234"
            result = node_decide(state)

        assert result["current_best"] == 0.4, (
            "current_best must update to the new metric when the experiment is better"
        )
        assert result["current_experiment"]["status"] == "keep"
        assert result["current_experiment"]["commit"] == "abc1234"
        mock_commit.assert_called_once()

    def test_evaluate_extracts_last_metric_occurrence(self, ar_state):
        """evaluate must extract the LAST occurrence of the metric from output
        (training scripts print per-epoch metrics; we want the final value).
        """
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
        assert result["current_metric"] == 0.42, (
            f"evaluate must extract the LAST occurrence (0.42), got: {result['current_metric']}"
        )

    def test_evaluate_returns_failed_when_metric_missing(self, ar_state):
        """evaluate must set status=failed when the metric is not in output."""
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

    def test_log_appends_to_ledger_and_history(self, ar_state, tmp_path):
        """log must append a row to results.tsv AND append to experiment_history."""
        from workflows.autoresearch_impl.nodes.log import node_log

        results_path = tmp_path / "results.tsv"
        # Pre-create with header (setup normally does this)
        results_path.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\n",
            encoding="utf-8",
        )
        state = dict(ar_state)
        state.update({
            "results_path": str(results_path),
            "experiment_count": 0,
            "experiment_history": [],
            "current_experiment": {
                "iteration": 1,
                "description": "test experiment",
                "metric": 0.45,
                "status": "keep",
                "commit": "abc1234",
            },
        })
        result = node_log(state)

        # experiment_count must increment
        assert result["experiment_count"] == 1
        # experiment_history must have the new entry
        assert len(result["experiment_history"]) == 1
        assert result["experiment_history"][0]["iteration"] == 1
        # current_experiment must be cleared for the next iteration
        assert result["current_experiment"] == {}
        # results.tsv must have the new row
        content = results_path.read_text(encoding="utf-8")
        assert "1\tabc1234\t0.45\tkeep\ttest experiment" in content, (
            f"results.tsv must contain the new row, got: {content!r}"
        )

    def test_modify_writes_new_content_atomically(self, ar_state, tmp_path):
        """modify must write the proposed new_content to target_file."""
        from workflows.autoresearch_impl.nodes.modify import node_modify

        target = tmp_path / "train.py"
        target.write_text("old content\n", encoding="utf-8")

        state = dict(ar_state)
        state.update({
            "target_file": "train.py",
            "project_root": str(tmp_path),
            "current_experiment": {
                "iteration": 1,
                "description": "rewrite",
                "new_content": "print('new content')\n",
            },
        })
        result = node_modify(state)
        assert result["status"] == "running"
        assert target.read_text(encoding="utf-8") == "print('new content')\n"

    def test_modify_skips_empty_proposal(self, ar_state):
        """modify must set status=failed when new_content is empty."""
        from workflows.autoresearch_impl.nodes.modify import node_modify

        state = dict(ar_state)
        state.update({
            "current_experiment": {
                "iteration": 1,
                "description": "broken proposal",
                "new_content": "",
            },
        })
        result = node_modify(state)
        assert result["status"] == "failed"
        assert "empty" in result["error"].lower()
