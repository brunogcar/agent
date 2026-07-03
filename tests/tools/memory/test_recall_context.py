"""Tests for the recall_context action.
v1.1: Added tags_filter limitation test.
"""
from __future__ import annotations

from tools.memory import memory


class TestRecallContextValidation:
    def test_missing_query_error(self, mock_cfg, mock_store):
        result = memory(action="recall_context", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        result = memory(action="recall_context", query="test", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]


class TestRecallContextSuccess:
    def test_returns_formatted_string(self, mock_cfg, mock_store):
        result = memory(action="recall_context", query="python")
        assert result["status"] == "success"
        assert "context" in result["data"]
        assert result["data"]["context"] == "Formatted memory context for prompt injection."
        mock_store.recall_context.assert_called_once()

    def test_with_collections(self, mock_cfg, mock_store):
        memory(action="recall_context", query="test", collections=["procedural"])
        call_kwargs = mock_store.recall_context.call_args.kwargs
        assert call_kwargs["collections"] == ["procedural"]

    def test_tags_filter_ignored(self, mock_cfg, mock_store):
        """v1.1: tags_filter is accepted by facade but not passed to backend recall_context.
        The backend execute_recall_context() does not support tags_filter or min_score.
        Use recall() for filtered searches."""
        memory(action="recall_context", query="test", tags_filter="mcp,howto")
        call_kwargs = mock_store.recall_context.call_args.kwargs
        assert "tags_filter" not in call_kwargs
        assert "min_score" not in call_kwargs
