"""Tests for the recall_context action.
v1.2: Added unsupported param rejection tests.
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

    def test_recall_context_rejects_tags_filter(self, mock_cfg, mock_store):
        """v1.2: recall_context must fail fast on unsupported tags_filter."""
        result = memory(action="recall_context", query="test", tags_filter="mcp")
        assert result["status"] == "error"
        assert "does not support tags_filter" in result["error"]

    def test_recall_context_rejects_min_score(self, mock_cfg, mock_store):
        """v1.2: recall_context must fail fast on unsupported min_score."""
        result = memory(action="recall_context", query="test", min_score=0.8)
        assert result["status"] == "error"
        assert "does not support min_score" in result["error"]

    def test_recall_context_default_min_score_allowed(self, mock_cfg, mock_store):
        """v1.2: Default min_score=0.5 must be allowed (not rejected)."""
        result = memory(action="recall_context", query="test", min_score=0.5)
        assert result["status"] == "success"

class TestRecallContextSuccess:
    def test_successful_recall_context(self, mock_cfg, mock_store):
        result = memory(action="recall_context", query="test query")
        assert result["status"] == "success"
        assert "context" in result["data"]
        mock_store.recall_context.assert_called_once()
