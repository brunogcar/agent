"""Tests for the recall action."""
from __future__ import annotations

from tools.memory import memory


class TestRecallValidation:
    def test_missing_query_error(self, mock_cfg, mock_store):
        result = memory(action="recall", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_invalid_tags_filter_error(self, mock_cfg, mock_store):
        result = memory(action="recall", query="test", tags_filter="bad<tag")
        assert result["status"] == "error"
        assert "cannot contain" in result["error"]

    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        result = memory(action="recall", query="test", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]


class TestRecallSuccess:
    def test_successful_recall(self, mock_cfg, mock_store):
        result = memory(action="recall", query="python", top_k=3)
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert len(result["data"]["results"]) == 1
        mock_store.recall.assert_called_once()

    def test_recall_with_collections(self, mock_cfg, mock_store):
        memory(action="recall", query="test", collections=["semantic"])
        call_kwargs = mock_store.recall.call_args.kwargs
        assert call_kwargs["collections"] == ["semantic"]

    def test_recall_with_tags_filter(self, mock_cfg, mock_store):
        memory(action="recall", query="test", tags_filter="mcp,howto")
        call_kwargs = mock_store.recall.call_args.kwargs
        assert call_kwargs["tags_filter"] == "mcp,howto"

    def test_trace_id_passed_to_recall(self, mock_cfg, mock_store):
        memory(action="recall", query="test", trace_id="abc123")
        call_kwargs = mock_store.recall.call_args.kwargs
        assert call_kwargs["trace_id"] == "abc123"
