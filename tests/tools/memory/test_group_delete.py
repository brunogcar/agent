"""Tests for the memory group delete by source_doc_id (v1.4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.memory import memory


@pytest.fixture
def mock_store():
    """Mock the memory store. Patches _mem in BOTH helpers AND the delete module
    (delete.py imports _mem at module level, so patching helpers alone isn't enough)."""
    store = MagicMock()
    # Only procedural collection has chunks; episodic/semantic return empty
    proc_col = MagicMock()
    proc_col.get.return_value = {
        "ids": ["chunk1", "chunk2", "chunk3"],
        "metadatas": [{"source_doc_id": "doc-uuid"}, {"source_doc_id": "doc-uuid"}, {"source_doc_id": "doc-uuid"}],
    }
    empty_col = MagicMock()
    empty_col.get.return_value = {"ids": [], "metadatas": []}
    # _col("procedural") returns proc_col; all others return empty_col
    store._col.side_effect = lambda name: proc_col if name == "procedural" else empty_col
    with patch("tools.memory_ops.helpers._mem", return_value=store), \
         patch("tools.memory_ops.actions.delete._mem", return_value=store):
        yield store


class TestGroupDelete:
    def test_delete_by_source_doc_id(self, mock_store):
        result = memory(action="delete", source_doc_id="doc-uuid")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "deleted"
        assert result["data"]["deleted"] == 3
        assert result["data"]["source_doc_id"] == "doc-uuid"

    def test_delete_by_source_doc_id_no_match(self, mock_store):
        # Override: no chunks found
        col = MagicMock()
        col.get.return_value = {"ids": [], "metadatas": []}
        mock_store._col.side_effect = lambda name: col
        result = memory(action="delete", source_doc_id="nonexistent-uuid")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "no_match"
        assert result["data"]["deleted"] == 0

    def test_delete_by_source_doc_id_missing_param(self, mock_store):
        """source_doc_id="" is falsy → falls through to the original delete path
        which requires query or confirm_ids. The original delete doesn't set
        error_code (pre-v1.4 behavior) — check the error message instead."""
        result = memory(action="delete", source_doc_id="")
        assert result["status"] == "error"
        assert "required" in result["error"]
