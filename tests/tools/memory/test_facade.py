"""Tests for the memory facade: dispatch, metadata, trace_id, compression."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.memory import memory
from tools.memory_ops import DISPATCH


class TestFacadeDispatch:
    def test_unknown_action_returns_error(self, mock_cfg, mock_store):
        result = memory(action="invalid_action")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "store" in result["error"]  # valid actions listed

    def test_empty_action_returns_error(self, mock_cfg, mock_store):
        result = memory(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"]

    def test_all_actions_registered(self):
        actions = DISPATCH.get("memory", {})
        expected = {
            "store", "recall", "recall_context", "delete",
            "prune", "summarize", "stats", "janitor",
        }
        assert set(actions.keys()) == expected

    def test_action_literal_in_annotations(self):
        from typing import get_type_hints
        hints = get_type_hints(memory)
        action_hint = hints.get("action")
        assert action_hint is not None
        # Should be a Literal type
        assert hasattr(action_hint, "__args__")


class TestFacadeTraceId:
    def test_trace_id_injected_into_success_result(self, mock_cfg, mock_store):
        result = memory(action="stats", trace_id="abc123")
        assert result["trace_id"] == "abc123"

    def test_trace_id_injected_into_error_result(self, mock_cfg, mock_store):
        result = memory(action="store", text="", trace_id="err-trace")
        assert result["trace_id"] == "err-trace"

    def test_trace_id_present_in_all_results(self, mock_cfg, mock_store):
        """Verify trace_id is always present in result, whether success or error."""
        success = memory(action="stats", trace_id="t1")
        error = memory(action="store", text="", trace_id="t2")
        assert success["trace_id"] == "t1"
        assert error["trace_id"] == "t2"


class TestFacadeCompression:
    def test_compress_result_applied_to_success(self, mock_cfg, mock_store):
        result = memory(action="stats")
        assert result["status"] == "success"
        # compress_result is a no-op on small dicts, just verify it doesn't crash

    def test_compress_result_applied_to_error(self, mock_cfg, mock_store):
        result = memory(action="store", text="")
        assert result["status"] == "error"
        # compress_result on fail dict should be safe
