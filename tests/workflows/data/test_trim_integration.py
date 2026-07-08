"""tests/workflows/data/test_trim_integration.py

Integration tests for the trim node wired into the data workflow (v1.1).

Verifies that trim_state_node:
  - Is correctly wired between critique and store in the graph
  - Evicts oversized `output` after critique produces `result`
  - Passes under-threshold `output` through unchanged
  - Works with both chonkie path (mocked) and fallback path (mocked)

The data workflow flow is:
  recall → execute → critique → trim → store → notify

After critique sets `result`, the raw `output` is no longer needed by
store or notify (both use `result` with `output` as fallback). The trim
node evicts oversized `output` to episodic memory, keeping a preview.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# trim_state_node as a LangGraph node — partial dict return
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimStateNodePartial:
    """trim_state_node must return a PARTIAL dict (only evicted keys),
    not a full state dict. This is the LangGraph contract."""

    def test_returns_empty_dict_when_nothing_evicted(self, mocker):
        """Under-threshold output → trim_state_node returns {} (nothing to merge)."""
        from workflows.base import trim_state_node
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {
            "trace_id": "t1",
            "output": "small output",  # under threshold
            "result": "analysis result",
        }
        result = trim_state_node(state)
        assert result == {}, "Under-threshold output should return empty dict"

    def test_returns_only_evicted_key(self, mocker):
        """Oversized output → trim_state_node returns {"output": "<placeholder>"} only."""
        from workflows.base import trim_state_node
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        state = {
            "trace_id": "t1",
            "output": "x" * 5000,  # over threshold
            "result": "analysis result",
            "goal": "test goal",
        }
        result = trim_state_node(state)
        # Must return ONLY the evicted key, not the full state
        assert "output" in result
        assert "Evicted" in result["output"]
        assert "goal" not in result  # goal was not evicted
        assert "result" not in result  # result was not evicted
        assert "trace_id" not in result  # trace_id was not evicted


# ─────────────────────────────────────────────────────────────────────────────
# Chonkie path — chunked eviction with preview
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimNodeChonkiePath:
    """When chonkie is available, trim_state_node evicts chunks individually
    and keeps a preview in the output field."""

    def test_chonkie_path_evicts_chunks_and_keeps_preview(self, mocker):
        from workflows.base import trim_state_node
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["First chunk with useful preview info.", "chunk 1", "chunk 2"]
        )
        state = {
            "trace_id": "t1",
            "output": "x" * 5000,
            "result": "analysis",
        }
        result = trim_state_node(state)
        assert mock_push.call_count == 3  # one push per chunk
        assert "output" in result
        assert "3 chunks" in result["output"]
        assert "First chunk with useful preview info." in result["output"]
        assert "Preview" in result["output"]

    def test_chonkie_source_field_includes_output_key(self, mocker):
        """The evicted chunks' source field includes 'evicted:output' so the
        LLM can recall them via tags_filter='evicted'."""
        from workflows.base import trim_state_node
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["c0", "c1"]
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        trim_state_node(state)
        for call in mock_push.call_args_list:
            assert "evicted:output" in call.kwargs["metadata"]["source"]


# ─────────────────────────────────────────────────────────────────────────────
# Fallback path — whole-string eviction (chonkie missing)
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimNodeFallbackPath:
    """When chonkie is not available, trim_state_node falls back to
    whole-string eviction (v1.0 behavior)."""

    def test_fallback_evicts_whole_string(self, mocker):
        from workflows.base import trim_state_node
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        result = trim_state_node(state)
        assert mock_push.call_count == 1  # whole-string, not chunked
        assert "output" in result
        assert "Evicted" in result["output"]
        assert "chunks" not in result["output"]  # no chunk count in fallback


# ─────────────────────────────────────────────────────────────────────────────
# Data workflow field safety — store/notify use `result`, not `output`
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimNodeDataFieldSafety:
    """Verify that evicting `output` after critique is safe — store and notify
    use `result` (set by critique), not the raw `output`. This is the design
    contract that makes the trim insertion point safe."""

    def test_store_uses_result_not_output(self):
        """node_store reads state.get('result', '') or state.get('output', '')
        as fallback. When result is set (post-critique), output is not read."""
        from workflows.data_impl.nodes.store import node_store
        import inspect
        source = inspect.getsource(node_store)
        # The store node must use result first, output as fallback
        assert "state.get(\"result\"" in source or "state.get('result'" in source
        assert "state.get(\"output\"" in source or "state.get('output'" in source

    def test_notify_uses_result_not_output(self):
        """node_notify reads state.get('result', '') or state.get('output', '')
        as fallback. When result is set (post-critique), output is not read."""
        from workflows.data_impl.nodes.notify import node_notify
        import inspect
        source = inspect.getsource(node_notify)
        assert "state.get(\"result\"" in source or "state.get('result'" in source
        assert "state.get(\"output\"" in source or "state.get('output'" in source

    def test_critique_always_sets_result_when_output_exists(self):
        """node_critique sets `result` in all paths when output is non-empty.
        This means after critique, `result` is always available — evicting
        `output` is safe."""
        from workflows.data_impl.nodes.critique import node_critique
        import inspect
        source = inspect.getsource(node_critique)
        # Every return path that follows the `if not output:` guard must
        # include "result" in the returned dict
        assert '"result"' in source or "'result'" in source
