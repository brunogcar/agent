"""tests/workflows/data/test_store.py
Tests for node_store — episodic + procedural storage, code_generated gating,
and graceful memory failure.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from workflows.data_impl.nodes.store import node_store


class TestNodeStore:
    def test_stores_episodic(self, base_state):
        base_state["result"] = "Top months: Jan, Mar"
        base_state["code"] = "print('x')"
        base_state["code_generated"] = True
        with patch("core.memory_engine.memory") as mock_memory:
            out = node_store(base_state)
        assert out == {}, "[Fix #1] node_store must return {} (side effects only)"
        mock_memory.store_episodic.assert_called_once()

    def test_stores_procedural_for_generated_code(self, base_state):
        """[Fix #5] LLM-generated code that worked is stored as procedural memory."""
        base_state["result"] = "6"
        base_state["code"] = "print(sum([1,2,3]))"
        base_state["code_generated"] = True
        with patch("core.memory_engine.memory") as mock_memory:
            node_store(base_state)
        mock_memory.store_procedural.assert_called_once()

    def test_does_not_store_procedural_for_user_code(self, base_state):
        """[Fix #5] User-provided code must NOT pollute procedural memory."""
        base_state["result"] = "6"
        base_state["code"] = "print(1)"
        base_state["code_generated"] = False
        with patch("core.memory_engine.memory") as mock_memory:
            node_store(base_state)
        mock_memory.store_episodic.assert_called_once()
        mock_memory.store_procedural.assert_not_called(), (
            "User-provided code must not be stored as procedural memory"
        )

    def test_does_not_store_procedural_when_flag_absent(self, base_state):
        """[Fix #5] Absent code_generated flag means user-provided code."""
        base_state["result"] = "6"
        base_state["code"] = "print(1)"
        with patch("core.memory_engine.memory") as mock_memory:
            node_store(base_state)
        mock_memory.store_procedural.assert_not_called()

    def test_no_result_returns_empty(self, base_state):
        base_state["result"] = ""
        with patch("core.memory_engine.memory") as mock_memory:
            out = node_store(base_state)
        assert out == {}
        mock_memory.store_episodic.assert_not_called()
        mock_memory.store_procedural.assert_not_called()

    def test_memory_failure_is_graceful(self, base_state):
        """[Fix #8] A memory backend failure must not crash the workflow."""
        base_state["result"] = "6"
        base_state["code"] = "print(1)"
        base_state["code_generated"] = True
        with patch("core.memory_engine.memory") as mock_memory, \
             patch("core.tracer.tracer.error") as mock_error:
            mock_memory.store_episodic.side_effect = RuntimeError("chromadb down")
            mock_memory.store_procedural.side_effect = RuntimeError("chromadb down")
            out = node_store(base_state)
        assert out == {}, "Memory failure must still return {}"
        assert mock_error.call_count >= 2, "Both store failures must be logged"
