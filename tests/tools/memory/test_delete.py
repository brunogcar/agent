"""Tests for the delete action.
v1.1: Added collections validation, confirm_ids-only, threshold=0.0 tests.
v1.2: Added confirm_ids type guard, threshold range tests.
"""
from __future__ import annotations

from tools.memory import memory

class TestDeleteValidation:
    def test_missing_query_and_confirm_ids_error(self, mock_cfg, mock_store):
        """v1.1: Both query and confirm_ids missing must fail."""
        result = memory(action="delete", query="")
        assert result["status"] == "error"
        assert "query or confirm_ids is required" in result["error"]

    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        """v1.1: Empty collections list must be rejected."""
        result = memory(action="delete", query="test", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]

    def test_collections_type_error(self, mock_cfg, mock_store):
        """v1.1: Non-list collections must be rejected."""
        result = memory(action="delete", query="test", collections="semantic")
        assert result["status"] == "error"
        assert "must be a list" in result["error"]

    def test_confirm_ids_string_rejected(self, mock_cfg, mock_store):
        """v1.2: String confirm_ids must be rejected to prevent character-wise iteration."""
        result = memory(action="delete", confirm_ids="abc123")
        assert result["status"] == "error"
        assert "confirm_ids must be a list" in result["error"]

    def test_threshold_out_of_range_rejected(self, mock_cfg, mock_store):
        """v1.2: threshold outside 0.0-1.0 must be rejected."""
        result = memory(action="delete", query="test", threshold=-0.1)
        assert result["status"] == "error"
        assert "threshold must be between 0.0 and 1.0" in result["error"]

        result = memory(action="delete", query="test", threshold=1.5)
        assert result["status"] == "error"
        assert "threshold must be between 0.0 and 1.0" in result["error"]

class TestDeleteSuccess:
    def test_successful_delete(self, mock_cfg, mock_store):
        result = memory(action="delete", query="old stuff")
        assert result["status"] == "success"
        mock_store.delete.assert_called_once()

    def test_delete_with_confirm_ids(self, mock_cfg, mock_store):
        memory(action="delete", query="test", confirm_ids=["id1", "id2"])
        call_kwargs = mock_store.delete.call_args.kwargs
        assert call_kwargs["confirm_ids"] == ["id1", "id2"]

    def test_delete_with_confirm_ids_only(self, mock_cfg, mock_store):
        """v1.1: delete with confirm_ids but no query should succeed."""
        result = memory(action="delete", confirm_ids=["id1", "id2"])
        assert result["status"] == "success"
        mock_store.delete.assert_called_once()

    def test_delete_with_threshold(self, mock_cfg, mock_store):
        memory(action="delete", query="test", threshold=0.7)
        call_kwargs = mock_store.delete.call_args.kwargs
        assert call_kwargs["threshold"] == 0.7

    def test_threshold_zero_not_none(self, mock_cfg, mock_store):
        """v1.1: threshold=0.0 must be passed as 0.0, not converted to None."""
        memory(action="delete", query="test", threshold=0.0)
        call_kwargs = mock_store.delete.call_args.kwargs
        assert call_kwargs["threshold"] == 0.0
