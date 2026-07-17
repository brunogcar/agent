"""Tests for the memory update action (v1.4)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tools.memory import memory


@pytest.fixture
def mock_store():
    """Mock the memory store for update tests.
    Patches _mem in BOTH helpers AND the update module (update.py imports _mem
    at module level, so patching helpers alone isn't enough)."""
    store = MagicMock()
    # Simulate a found memory
    col = MagicMock()
    col.get.return_value = {
        "ids": ["abc123"],
        "documents": ["When parsing JSON, handle JSONDecodeError"],
        "metadatas": [{"importance": 5, "tags": "source:sleep_learn", "version": 1}],
    }
    store._col.return_value = col
    with patch("tools.memory_ops.helpers._mem", return_value=store), \
         patch("tools.memory_ops.actions.update._mem", return_value=store):
        with patch("tools.memory_ops.actions.update._get_audit_db") as mock_audit:
            mock_conn = MagicMock()
            mock_audit.return_value = mock_conn
            yield store, mock_conn


class TestUpdateAction:
    def test_update_single_field(self, mock_store):
        store, audit_conn = mock_store
        result = memory(
            action="update",
            id="abc123",
            fields={"importance": 8},
            reason="reinforced after success",
        )
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "updated"
        assert "importance" in result["data"]["changed_fields"]
        assert result["data"]["version"] == 2  # incremented
        # Audit log was written
        assert audit_conn.execute.called
        audit_conn.commit.assert_called()

    def test_update_multiple_fields(self, mock_store):
        store, audit_conn = mock_store
        result = memory(
            action="update",
            id="abc123",
            fields={"importance": 9, "tags": "source:sleep_learn,confidence:high"},
            reason="boosted",
        )
        assert result["status"] == "success"
        assert "importance" in result["data"]["changed_fields"]
        assert "tags" in result["data"]["changed_fields"]

    def test_update_missing_id(self, mock_store):
        result = memory(action="update", fields={"importance": 8}, reason="test")
        assert result["status"] == "error"
        assert result["error_code"] == "MISSING_PARAM"

    def test_update_missing_fields(self, mock_store):
        result = memory(action="update", id="abc123", reason="test")
        assert result["status"] == "error"
        assert result["error_code"] == "MISSING_PARAM"

    def test_update_missing_reason(self, mock_store):
        result = memory(action="update", id="abc123", fields={"importance": 8})
        assert result["status"] == "error"
        assert result["error_code"] == "MISSING_PARAM"

    def test_update_invalid_field(self, mock_store):
        result = memory(
            action="update", id="abc123",
            fields={"nonexistent_field": "value"}, reason="test",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_PARAM"

    def test_update_importance_out_of_range(self, mock_store):
        result = memory(
            action="update", id="abc123",
            fields={"importance": 15}, reason="test",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_PARAM"

    def test_update_confidence_out_of_range(self, mock_store):
        result = memory(
            action="update", id="abc123",
            fields={"confidence": 1.5}, reason="test",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_PARAM"

    def test_update_not_found(self, mock_store):
        store, audit_conn = mock_store
        # Override: memory not found
        col = MagicMock()
        col.get.return_value = {"ids": [], "documents": [], "metadatas": []}
        store._col.return_value = col
        # Also need to re-patch since the fixture's patches are already active
        with patch("tools.memory_ops.actions.update._mem", return_value=store):
            result = memory(
                action="update", id="nonexistent",
                fields={"importance": 8}, reason="test",
            )
        assert result["status"] == "error"
        assert result["error_code"] == "NOT_FOUND"

    def test_update_noop_when_values_unchanged(self, mock_store):
        store, audit_conn = mock_store
        # importance is already 5 in the mock — set it to 5 again
        result = memory(
            action="update", id="abc123",
            fields={"importance": 5}, reason="test",
        )
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "noop"
        assert result["data"]["changed_fields"] == []
