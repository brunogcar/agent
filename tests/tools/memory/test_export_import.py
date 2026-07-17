"""Tests for the memory export/import actions (v1.4)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.memory import memory


@pytest.fixture
def mock_store():
    """Mock the memory store with sample data."""
    store = MagicMock()

    # Mock collection with 2 memories
    col = MagicMock()
    col.get.return_value = {
        "ids": ["id1", "id2"],
        "documents": ["rule one", "rule two"],
        "metadatas": [{"importance": 7}, {"importance": 5}],
    }
    store._col.return_value = col
    with patch("tools.memory_ops.helpers._mem", return_value=store):
        yield store


class TestExportAction:
    def test_export_writes_jsonl(self, mock_store, tmp_path):
        out = tmp_path / "export.jsonl"
        result = memory(action="export", output_path=str(out))
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "exported"
        assert result["data"]["count"] > 0
        assert out.exists()
        # Verify JSONL format
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            entry = json.loads(line)
            assert "id" in entry
            assert "document" in entry
            assert "metadata" in entry
            assert "collection" in entry

    def test_export_specific_collections(self, mock_store, tmp_path):
        out = tmp_path / "procedural.jsonl"
        result = memory(
            action="export",
            collections=["procedural"],
            output_path=str(out),
        )
        assert result["status"] == "success"
        assert "procedural" in result["data"]["by_collection"]


class TestImportAction:
    def test_import_reads_jsonl(self, mock_store, tmp_path):
        # Create a test JSONL file
        inp = tmp_path / "import.jsonl"
        inp.write_text(
            json.dumps({"id": "new1", "document": "new rule", "metadata": {"importance": 8}, "collection": "procedural"}) + "\n" +
            json.dumps({"id": "new2", "document": "another rule", "metadata": {"importance": 6}, "collection": "semantic"}) + "\n",
            encoding="utf-8",
        )
        result = memory(action="import", input_path=str(inp))
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "imported"
        assert result["data"]["imported"] == 2

    def test_import_missing_file(self, mock_store):
        result = memory(action="import", input_path="nonexistent.jsonl")
        assert result["status"] == "error"
        assert result["error_code"] == "NOT_FOUND"

    def test_import_missing_path(self, mock_store):
        result = memory(action="import")
        assert result["status"] == "error"
        assert result["error_code"] == "MISSING_PARAM"

    def test_import_with_collection_filter(self, mock_store, tmp_path):
        inp = tmp_path / "import.jsonl"
        inp.write_text(
            json.dumps({"id": "p1", "document": "proc rule", "metadata": {"importance": 5}, "collection": "procedural"}) + "\n" +
            json.dumps({"id": "s1", "document": "sem rule", "metadata": {"importance": 3}, "collection": "semantic"}) + "\n",
            encoding="utf-8",
        )
        result = memory(action="import", input_path=str(inp), collections=["procedural"])
        assert result["status"] == "success"
        assert result["data"]["imported"] == 1  # only procedural
        assert result["data"]["skipped"] == 1  # semantic filtered out
