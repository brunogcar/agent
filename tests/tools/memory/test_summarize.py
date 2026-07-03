"""Tests for the summarize action.
v1.1: Added collections validation test.
"""
from __future__ import annotations

from tools.memory import memory


class TestSummarizeValidation:
    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        """v1.1: Empty collections list must be rejected."""
        result = memory(action="summarize", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]


class TestSummarizeSuccess:
    def test_summarize(self, mock_cfg, mock_store):
        result = memory(action="summarize")
        assert result["status"] == "success"
        mock_store.summarize.assert_called_once()

    def test_summarize_with_collections(self, mock_cfg, mock_store):
        memory(action="summarize", collections=["procedural"])
        call_kwargs = mock_store.summarize.call_args.kwargs
        assert call_kwargs["collections"] == ["procedural"]

    def test_trace_id_passed_to_summarize(self, mock_cfg, mock_store):
        """v1.1: trace_id must be passed to backend summarize."""
        memory(action="summarize", trace_id="abc123")
        call_kwargs = mock_store.summarize.call_args.kwargs
        assert call_kwargs["trace_id"] == "abc123"
