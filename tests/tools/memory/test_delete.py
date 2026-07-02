"""Tests for the delete action."""
from __future__ import annotations

from tools.memory import memory


class TestDeleteValidation:
    def test_missing_query_error(self, mock_cfg, mock_store):
        result = memory(action="delete", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]


class TestDeleteSuccess:
    def test_successful_delete(self, mock_cfg, mock_store):
        result = memory(action="delete", query="old stuff")
        assert result["status"] == "success"
        mock_store.delete.assert_called_once()

    def test_delete_with_confirm_ids(self, mock_cfg, mock_store):
        memory(action="delete", query="test", confirm_ids=["id1", "id2"])
        call_kwargs = mock_store.delete.call_args.kwargs
        assert call_kwargs["confirm_ids"] == ["id1", "id2"]

    def test_delete_with_threshold(self, mock_cfg, mock_store):
        memory(action="delete", query="test", threshold=0.7)
        call_kwargs = mock_store.delete.call_args.kwargs
        assert call_kwargs["threshold"] == 0.7
