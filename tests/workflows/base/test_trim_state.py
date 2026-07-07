"""tests/workflows/base/test_trim_state.py
Tests for trim_state() — memory eviction of oversized fields.
"""
from __future__ import annotations


class TestTrimState:
    def test_evicts_oversized_fields(self, mocker):
        from workflows.base import trim_state
        mock_push = mocker.patch("core.memory_backend.eviction.eviction_queue.push")
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
        assert mock_push.call_count == 1  # only search_results was evicted

    def test_returns_new_dict(self, base_state):
        from workflows.base import trim_state
        result = trim_state(base_state)
        assert result is not base_state, "trim_state must return a new dict (Copy-on-Write)"

    def test_preserves_unchanged_fields(self, base_state):
        from workflows.base import trim_state
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
        state = {
            "trace_id": "t1",
            "search_results": ["a"] * 5000,  # list, not string
            "output": {"big": "dict"},
        }
        result = trim_state(state)
        assert not mock_push.called, "Non-string fields should not be evicted"
