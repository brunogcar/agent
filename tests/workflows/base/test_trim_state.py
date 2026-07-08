"""tests/workflows/base/test_trim_state.py
Tests for trim_state() — memory eviction of oversized fields.

v1.3: Added chonkie-aware eviction tests. The chonkie path splits oversized
fields into sentence-aware chunks and evicts each individually. The fallback
path (chonkie missing or chunking fails) does whole-string eviction (v1.0 behavior).

Test design:
  - ALL tests mock _chunk_text to control which path is exercised. This makes
    tests deterministic regardless of whether chonkie is installed.
  - Fallback tests: mock _chunk_text to raise RuntimeError (simulate chonkie missing)
  - Chonkie tests: mock _chunk_text to return a controlled list of chunks
  - Single-chunk test: mock _chunk_text to return [val] (falls back to whole-string)
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Fallback path (v1.0 behavior — chonkie missing or chunking fails)
# All tests in this section mock _chunk_text to raise RuntimeError, forcing
# the whole-string eviction path.
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimStateFallback:
    """Whole-string eviction when chonkie is not available."""

    def test_evicts_oversized_fields(self, mocker):
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        # Force fallback path (chonkie not available)
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {
            "trace_id": "t1",
            "search_results": "x" * 5000,  # > 1000 tokens (~4000 chars)
            "output": "short",
            "analysis": "",
        }
        result = trim_state(state)
        assert "Evicted" in result["search_results"]
        assert result["output"] == "short"  # under threshold
        assert result["analysis"] == ""  # empty
        assert mock_push.call_count == 1  # whole-string eviction (fallback)

    def test_returns_new_dict(self, base_state, mocker):
        from workflows.base import trim_state
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        result = trim_state(base_state)
        assert result is not base_state, "trim_state must return a new dict (Copy-on-Write)"

    def test_preserves_unchanged_fields(self, base_state, mocker):
        from workflows.base import trim_state
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        base_state["search_results"] = "short"  # under threshold
        result = trim_state(base_state)
        assert result["search_results"] == "short"
        assert result["goal"] == base_state["goal"]
        assert result["trace_id"] == base_state["trace_id"]

    def test_eviction_threshold(self, mocker):
        """Fields over ~4000 chars (~1000 tokens) are evicted.

        Threshold: (len(val) // 4) > 1000, so len(val) must be > 4000.
        4001 // 4 = 1000 (not > 1000). 4005 // 4 = 1001 (> 1000). So 4005 triggers.
        """
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        # 4001 chars → 4001 // 4 = 1000, NOT > 1000 → not evicted
        state_under = {"trace_id": "t1", "output": "x" * 4001}
        trim_state(state_under)
        assert not mock_push.called
        # 4005 chars → 4005 // 4 = 1001, > 1000 → evicted
        state_over = {"trace_id": "t1", "output": "x" * 4005}
        trim_state(state_over)
        assert mock_push.called

    def test_non_string_fields_not_evicted(self, mocker):
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {
            "trace_id": "t1",
            "search_results": ["a"] * 5000,  # list, not string
            "output": {"big": "dict"},
        }
        result = trim_state(state)
        assert not mock_push.called, "Non-string fields should not be evicted"

    def test_fallback_source_field_includes_key(self, mocker):
        """v1.3: The fallback path's source field includes the evicted key name."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            side_effect=RuntimeError("chonkie not installed")
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        trim_state(state)
        # Check the source metadata includes "evicted:output"
        call_kwargs = mock_push.call_args
        assert "evicted:output" in call_kwargs.kwargs["metadata"]["source"]


# ─────────────────────────────────────────────────────────────────────────────
# Chonkie path (v1.3 — chunked eviction)
# All tests in this section mock _chunk_text to return controlled chunks.
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimStateChonkie:
    """v1.3: Chonkie-aware eviction splits oversized fields into sentence-aware
    chunks and evicts each individually."""

    def test_chunks_evicted_individually(self, mocker):
        """When chonkie produces N chunks, eviction_queue.push is called N times
        (one per chunk), not once (whole-string)."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        # Mock chonkie to return 3 chunks
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["chunk 0 text", "chunk 1 text", "chunk 2 text"]
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        result = trim_state(state)
        assert mock_push.call_count == 3  # one push per chunk
        assert "Evicted" in result["output"]
        assert "3 chunks" in result["output"]

    def test_preview_kept_in_state(self, mocker):
        """The first chunk is kept as a preview in the state field."""
        from workflows.base import trim_state
        mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["First chunk preview text here.", "chunk 1", "chunk 2"]
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        result = trim_state(state)
        assert "First chunk preview text here." in result["output"]
        assert "Preview" in result["output"]

    def test_chunk_source_field_encodes_position(self, mocker):
        """Each chunk's source field encodes its position (chunk_N_of_M)."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["c0", "c1", "c2", "c3"]
        )
        state = {"trace_id": "t1", "analysis": "x" * 5000}
        trim_state(state)
        # Verify each push has the correct chunk_N_of_M source
        sources = [call.kwargs["metadata"]["source"] for call in mock_push.call_args_list]
        assert "evicted:analysis:chunk_0_of_4" in sources
        assert "evicted:analysis:chunk_1_of_4" in sources
        assert "evicted:analysis:chunk_2_of_4" in sources
        assert "evicted:analysis:chunk_3_of_4" in sources

    def test_single_chunk_falls_back_to_whole_string(self, mocker):
        """If chonkie returns only 1 chunk, fall back to whole-string eviction
        (no point chunking if there's only 1 chunk)."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        val = "x" * 5000
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=[val]  # single chunk
        )
        state = {"trace_id": "t1", "output": val}
        result = trim_state(state)
        assert mock_push.call_count == 1  # whole-string, not chunked
        assert "Evicted" in result["output"]
        assert "chunks" not in result["output"]  # no chunk count in placeholder

    def test_empty_chunks_falls_back(self, mocker):
        """If chonkie returns empty list, fall back to whole-string eviction."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=[]
        )
        state = {"trace_id": "t1", "output": "x" * 5000}
        trim_state(state)
        assert mock_push.call_count == 1  # whole-string fallback

    def test_trace_id_passed_to_all_chunks(self, mocker):
        """Each chunk push includes the trace_id in metadata."""
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
        mocker.patch(
            "tools.file_ops.actions.read_file._chunk_text",
            return_value=["c0", "c1"]
        )
        state = {"trace_id": "my-trace-123", "output": "x" * 5000}
        trim_state(state)
        for call in mock_push.call_args_list:
            assert call.kwargs["metadata"]["trace_id"] == "my-trace-123"
