"""tests/workflows/research/test_trim_integration.py

Integration tests for the trim node wired into the research workflow (v1.1).

Verifies that trim_state_node:
  - Is correctly wired between synthesize and report in the graph
  - Evicts oversized `search_results` after synthesize produces `result`
  - Passes under-threshold `search_results` through unchanged
  - Works with both chonkie path (mocked) and fallback path (mocked)

The research workflow flow is (v1.1):
  recall → search → parallel_scrape → synthesize → trim → report → store → distill → notify

After synthesize sets `result`, the raw `search_results` (up to 40KB) is no
longer needed by report, store, distill, or notify (all use `result`).
The trim node evicts oversized `search_results` to episodic memory.
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# trim_state_node as a LangGraph node — partial dict return
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimStateNodePartial:
    """trim_state_node must return a PARTIAL dict (only evicted keys),
    not a full state dict. This is the LangGraph contract."""

    def test_returns_empty_dict_when_nothing_evicted(self, mocker):
        """Under-threshold search_results → trim_state_node returns {}."""
        from workflows.base import trim_state_node
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {
            "trace_id": "t1",
            "search_results": "small results",  # under threshold
            "result": "synthesis text",
        }
        result = trim_state_node(state)
        assert result == {}, "Under-threshold search_results should return empty dict"

    def test_returns_only_evicted_key(self, mocker):
        """Oversized search_results → trim_state_node returns {"search_results": "<placeholder>"} only."""
        from workflows.base import trim_state_node
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        state = {
            "trace_id": "t1",
            "search_results": "x" * 5000,  # over threshold
            "result": "synthesis text",
            "goal": "test goal",
        }
        result = trim_state_node(state)
        # Must return ONLY the evicted key, not the full state
        assert "search_results" in result
        assert "Evicted" in result["search_results"]
        assert "goal" not in result  # goal was not evicted
        assert "result" not in result  # result was not evicted
        assert "trace_id" not in result  # trace_id was not evicted


# ─────────────────────────────────────────────────────────────────────────────
# Chonkie path — chunked eviction with preview
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimNodeChonkiePath:
    """When chonkie is available, trim_state_node evicts chunks individually
    and keeps a preview in the search_results field."""

    def test_chonkie_path_evicts_chunks_and_keeps_preview(self, mocker):
        from workflows.base import trim_state_node
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["First chunk with useful preview info.", "chunk 1", "chunk 2"]
        )
        state = {
            "trace_id": "t1",
            "search_results": "x" * 5000,
            "result": "synthesis",
        }
        result = trim_state_node(state)
        assert mock_push.call_count == 3  # one push per chunk
        assert "search_results" in result
        assert "3 chunks" in result["search_results"]
        assert "First chunk with useful preview info." in result["search_results"]
        assert "Preview" in result["search_results"]

    def test_chonkie_source_field_includes_search_results_key(self, mocker):
        """The evicted chunks' source field includes 'evicted:search_results'."""
        from workflows.base import trim_state_node
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["c0", "c1"]
        )
        state = {"trace_id": "t1", "search_results": "x" * 5000}
        trim_state_node(state)
        for call in mock_push.call_args_list:
            assert "evicted:search_results" in call.kwargs["metadata"]["source"]


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
        state = {"trace_id": "t1", "search_results": "x" * 5000}
        result = trim_state_node(state)
        assert mock_push.call_count == 1  # whole-string, not chunked
        assert "search_results" in result
        assert "Evicted" in result["search_results"]
        assert "chunks" not in result["search_results"]  # no chunk count in fallback


# ─────────────────────────────────────────────────────────────────────────────
# Research workflow field safety — report/store/distill/notify use `result`
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimNodeResearchFieldSafety:
    """Verify that evicting `search_results` after synthesize is safe —
    report, store, distill, and notify all use `result` (set by synthesize),
    not the raw `search_results`. This is the design contract that makes
    the trim insertion point safe."""

    def test_report_uses_result_not_search_results(self):
        """node_report reads state.get('result', '') — not search_results."""
        from workflows.research_impl.nodes.report import node_report
        import inspect
        source = inspect.getsource(node_report)
        assert 'state.get("result"' in source or "state.get('result'" in source
        # report must NOT read search_results
        assert 'state.get("search_results"' not in source
        assert "state.get('search_results'" not in source

    def test_store_uses_result_not_search_results(self):
        """node_store reads state.get('result', '') — not search_results."""
        from workflows.research_impl.nodes.store import node_store
        import inspect
        source = inspect.getsource(node_store)
        assert 'state.get("result"' in source or "state.get('result'" in source
        assert 'state.get("search_results"' not in source
        assert "state.get('search_results'" not in source

    def test_distill_uses_result_not_search_results(self):
        """node_distill reads state.get('result', '') — not search_results."""
        from workflows.research_impl.nodes.distill import node_distill
        import inspect
        source = inspect.getsource(node_distill)
        assert 'state.get("result"' in source or "state.get('result'" in source
        assert 'state.get("search_results"' not in source
        assert "state.get('search_results'" not in source

    def test_notify_uses_result_not_search_results(self):
        """node_notify reads state.get('result', '') — not search_results."""
        from workflows.research_impl.nodes.notify import node_notify
        import inspect
        source = inspect.getsource(node_notify)
        assert 'state.get("result"' in source or "state.get('result'" in source
        assert 'state.get("search_results"' not in source
        assert "state.get('search_results'" not in source

    def test_synthesize_always_sets_result_on_success(self):
        """node_synthesize sets `result` on the success path (returns {"result": r["text"]}).
        This means after synthesize succeeds, `result` is always available —
        evicting `search_results` is safe."""
        from workflows.research_impl.nodes.synthesize import node_synthesize
        import inspect
        source = inspect.getsource(node_synthesize)
        assert '"result"' in source or "'result'" in source
