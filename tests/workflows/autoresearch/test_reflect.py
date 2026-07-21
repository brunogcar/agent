"""Tests for v1.5 reflect node + cross-run learning.

Covers:
  node_reflect                — no-op on non-reflect iterations, reflects on
                                interval, disabled when interval=0, non-fatal
                                on LLM failure
  node_propose with reflection — reflect_notes folded into the proposal prompt
  node_decide cross-run learning — stores procedural memory on discard

ChromaDB is not installed in this test environment, so we inject a fake
`core.memory_engine` module via `patch.dict("sys.modules", ...)` for the
cross-run-learning tests. This mirrors the production code path —
`_record_failure_memory` lazily imports `from core.memory_engine import memory`,
so injecting the fake module makes the lazy import resolve to the mock without
ever touching the real (chromadb-dependent) MemoryStore.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager

import pytest
from unittest.mock import patch, MagicMock


@contextmanager
def _patched_memory_engine():
    """Inject a fake `core.memory_engine` module so tests can verify
    memory.recall / store_procedural calls without requiring chromadb.

    Yields the mock `memory` object. Configure its `.recall.return_value`
    / `.store_procedural.return_value` BEFORE calling the code under test.
    """
    mock_mem = MagicMock()
    fake_module = MagicMock()
    fake_module.memory = mock_mem
    # patch.dict replaces sys.modules["core.memory_engine"] for the duration
    # of the `with` block. The lazy `from core.memory_engine import memory`
    # inside _record_failure_memory then resolves to `mock_mem`.
    with patch.dict("sys.modules", {"core.memory_engine": fake_module}):
        yield mock_mem


class TestReflectNode:
    """Test node_reflect."""

    def test_noop_on_non_reflect_iteration(self, ar_state):
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        ar_state["experiment_count"] = 3  # not divisible by 5 (default interval)
        result = node_reflect(ar_state)
        assert result == {}

    def test_noop_on_zero_experiment_count(self, ar_state):
        """experiment_count=0 must NOT reflect (no history to reflect on)."""
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        ar_state["experiment_count"] = 0
        result = node_reflect(ar_state)
        assert result == {}

    def test_reflects_on_interval(self, ar_state):
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        ar_state["experiment_count"] = 10  # divisible by 5
        ar_state["experiment_history"] = [
            {"iteration": 1, "status": "keep", "metric": 0.5, "description": "test"},
        ]
        with patch("workflows.autoresearch_impl.nodes.reflect._call_planner") as mock_call:
            # [v1.8 N6] _call_planner now returns (response, usage) tuple.
            mock_call.return_value = ("Reflection: try different learning rates.", {"total": 100})
            result = node_reflect(ar_state)
        assert "reflect_notes" in result
        assert "Reflection" in result["reflect_notes"]
        # The planner must have been called exactly once with the reflection
        # system prompt + the user prompt that includes the history entry.
        mock_call.assert_called_once()
        _, user, _ = mock_call.call_args[0]
        assert "Goal:" in user
        assert "Metric:" in user
        assert "#1 [keep]" in user  # the history entry we set

    def test_disabled_when_interval_zero(self, ar_state, monkeypatch):
        """[v1.5 N1] AUTORESEARCH_REFLECT_INTERVAL=0 disables reflection entirely."""
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        # Use monkeypatch.setattr on the real cfg object so the imported
        # `from core.config import cfg` binding in reflect.py picks it up
        # (mirrors the existing pattern in test_nodes_propose.py).
        import core.config
        monkeypatch.setattr(core.config.cfg, "autoresearch_reflect_interval", 0)
        ar_state["experiment_count"] = 10  # would normally trigger reflect
        result = node_reflect(ar_state)
        assert result == {}

    def test_reflect_failure_is_non_fatal(self, ar_state):
        """If _call_planner raises, node_reflect returns {} (loop continues)."""
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        ar_state["experiment_count"] = 5
        with patch(
            "workflows.autoresearch_impl.nodes.reflect._call_planner",
            side_effect=RuntimeError("LLM failed"),
        ):
            result = node_reflect(ar_state)
        assert result == {}  # non-fatal — returns empty

    def test_reflect_builds_user_prompt_with_history(self, ar_state):
        """The user prompt passed to _call_planner must include the history."""
        from workflows.autoresearch_impl.nodes.reflect import node_reflect
        ar_state["experiment_count"] = 5
        ar_state["experiment_history"] = [
            {"iteration": 1, "status": "keep", "metric": 0.5, "description": "lr=1e-4"},
            {"iteration": 2, "status": "discard", "metric": 0.6, "description": "lr=1e-2"},
        ]
        with patch("workflows.autoresearch_impl.nodes.reflect._call_planner",
                   return_value=("NEXT STRATEGY: try AdamW", {"total": 50})) as mock_call:
            node_reflect(ar_state)
        _, user, _ = mock_call.call_args[0]
        # Both history entries must appear in the prompt (so the LLM has full context).
        assert "#1 [keep]" in user and "lr=1e-4" in user
        assert "#2 [discard]" in user and "lr=1e-2" in user


class TestProposeWithReflection:
    """Test that propose includes reflection notes in the prompt."""

    def test_reflect_notes_included_in_prompt(self, ar_state):
        """When state['reflect_notes'] is set, it must appear in the user prompt."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        ar_state["reflect_notes"] = "Try different optimizer."
        ar_state["experiment_count"] = 5
        # Write a stub train.py so _read_target_file returns something sensible.
        import pathlib
        pathlib.Path(ar_state["project_root"], "train.py").write_text(
            "print('hi')\n", encoding="utf-8",
        )
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner") as mock_call:
            # [v1.8 N6] _call_planner now returns (response, usage) tuple.
            mock_call.return_value = (
                '{"description": "test", "rationale": "test", "new_content": "print(1)"}',
                {"total": 0},
            )
            node_propose(ar_state)
            # Check the user prompt includes the reflection
            call_args = mock_call.call_args
            user_prompt = call_args[0][1] if call_args[0] else call_args[1].get("user", "")
            assert "Try different optimizer" in user_prompt

    def test_no_reflect_block_when_notes_empty(self, ar_state):
        """When reflect_notes is empty, the prompt must NOT include the strategist block."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        ar_state["reflect_notes"] = ""  # explicit empty
        ar_state["experiment_count"] = 0
        import pathlib
        pathlib.Path(ar_state["project_root"], "train.py").write_text(
            "print('hi')\n", encoding="utf-8",
        )
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner") as mock_call:
            # [v1.8 N6] _call_planner now returns (response, usage) tuple.
            mock_call.return_value = (
                '{"description": "test", "rationale": "test", "new_content": "print(1)"}',
                {"total": 0},
            )
            node_propose(ar_state)
            call_args = mock_call.call_args
            user_prompt = call_args[0][1] if call_args[0] else call_args[1].get("user", "")
            assert "Strategist reflection" not in user_prompt


class TestCrossRunLearning:
    """Test that decide stores procedural memory on failures.

    Uses `_patched_memory_engine()` to inject a fake `core.memory_engine`
    module — required because chromadb isn't installed in the test
    environment, so the real `core.memory_engine` import raises.
    """

    def test_stores_memory_on_discard(self, ar_state):
        """When an experiment is discarded (no improvement), a procedural
        memory must be stored so future runs can avoid re-proposing it."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.6  # worse than best (lower is better)
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["current_experiment"] = {"description": "increase LR", "iteration": 1}
        ar_state["project_root"] = ""  # avoid git operations

        with patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             _patched_memory_engine() as mock_mem:
            mock_mem.recall.return_value = []  # no existing memory
            mock_mem.store_procedural.return_value = {"status": "stored"}
            node_decide(ar_state)
            # Should have called store_procedural with the failed-proposal text.
            assert mock_mem.store_procedural.called
            call_kwargs = mock_mem.store_procedural.call_args
            # The text must reference the discarded proposal description.
            text = call_kwargs.kwargs.get("text", "") or call_kwargs[1].get("text", "")
            assert "increase LR" in text
            assert call_kwargs.kwargs.get("outcome") == "failure" or \
                   call_kwargs[1].get("outcome") == "failure"

    def test_no_store_on_keep(self, ar_state):
        """When an experiment is kept (improvement), NO procedural memory is stored."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.4  # better than best (lower is better)
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["current_experiment"] = {"description": "decrease LR", "iteration": 1}
        ar_state["project_root"] = ""

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"), \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard"), \
             _patched_memory_engine() as mock_mem:
            mock_mem.recall.return_value = []
            mock_mem.store_procedural.return_value = {"status": "stored"}
            node_decide(ar_state)
            # Should NOT have called store_procedural — keep is a success.
            assert not mock_mem.store_procedural.called

    def test_repeated_failure_does_not_re_store(self, ar_state):
        """When memory.recall finds an existing entry, don't store a duplicate."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.6
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["current_experiment"] = {"description": "increase LR", "iteration": 1}
        ar_state["project_root"] = ""

        with patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             _patched_memory_engine() as mock_mem:
            # Simulate "we've seen this failure before" — recall returns a hit.
            mock_mem.recall.return_value = [{"text": "prior failure note", "score": 0.9}]
            mock_mem.store_procedural.return_value = {"status": "stored"}
            node_decide(ar_state)
            # Should NOT have called store_procedural — failure already known.
            assert not mock_mem.store_procedural.called

    def test_memory_failure_is_non_fatal(self, ar_state):
        """If memory.recall raises, node_decide must still complete normally."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        ar_state["current_metric"] = 0.6
        ar_state["current_best"] = 0.5
        ar_state["metric_direction"] = "lower"
        ar_state["current_experiment"] = {"description": "increase LR", "iteration": 1}
        ar_state["project_root"] = ""

        with patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True), \
             _patched_memory_engine() as mock_mem:
            mock_mem.recall.side_effect = RuntimeError("chromadb down")
            # Must not raise — the loop continues.
            result = node_decide(ar_state)
        assert result["current_experiment"]["status"] == "discard"
        assert result["status"] == "running"
