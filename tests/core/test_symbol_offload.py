"""Tests for the symbol offloading utility."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from core.symbol_offload import (
    offload_to_file,
    drill_down,
    is_symbol_ref,
    _auto_summary,
)


class TestOffloadToFile:
    def test_offload_list(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            content = [{"iteration": 1, "tests_passed": False}, {"iteration": 2, "tests_passed": True}]
            ref = offload_to_file("trace-1", "debug_history", content)
            assert ref["_symbol_ref"] == "debug_history"
            assert ref["_symbol_file"].endswith("debug_history.json")
            assert "2 entries" in ref["_symbol_summary"]

    def test_offload_dict(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            content = {"key1": "val1", "key2": "val2", "key3": "val3"}
            ref = offload_to_file("trace-1", "config", content)
            assert "3 keys" in ref["_symbol_summary"]

    def test_offload_writes_file(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            content = ["a", "b", "c"]
            ref = offload_to_file("trace-1", "test_field", content)
            file_path = Path(ref["_symbol_file"])
            assert file_path.exists()
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            assert loaded == content

    def test_offload_custom_summary(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            ref = offload_to_file("trace-1", "field", ["x"], summary="custom summary")
            assert ref["_symbol_summary"] == "custom summary"

    def test_offload_size(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            content = "x" * 1000
            ref = offload_to_file("trace-1", "text", content)
            assert ref["_symbol_size"] > 1000


class TestDrillDown:
    def test_drill_down_returns_content(self, tmp_path):
        with patch("core.symbol_offload.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            content = [{"a": 1}, {"b": 2}]
            ref = offload_to_file("trace-1", "field", content)
            result = drill_down(ref)
            assert result == content

    def test_drill_down_missing_file(self, tmp_path):
        ref = {"_symbol_ref": "field", "_symbol_file": "/nonexistent/path.json"}
        assert drill_down(ref) is None

    def test_drill_down_empty_ref(self):
        assert drill_down({}) is None


class TestIsSymbolRef:
    def test_valid_symbol_ref(self):
        assert is_symbol_ref({"_symbol_ref": "x", "_symbol_file": "/path"})

    def test_plain_dict(self):
        assert not is_symbol_ref({"key": "value"})

    def test_not_dict(self):
        assert not is_symbol_ref("string")
        assert not is_symbol_ref([1, 2, 3])

    def test_partial_symbol_ref(self):
        assert not is_symbol_ref({"_symbol_ref": "x"})  # missing _symbol_file


class TestAutoSummary:
    def test_empty_list(self):
        assert _auto_summary([]) == "empty list"

    def test_list_with_tests_passed(self):
        content = [{"tests_passed": True}, {"tests_passed": False}, {"tests_passed": True}]
        summary = _auto_summary(content)
        assert "3 entries" in summary
        assert "2 passed" in summary
        assert "1 failed" in summary

    def test_list_of_rules(self):
        content = [{"rule": "test"}, {"rule": "test2"}]
        assert "2 rules" in _auto_summary(content)

    def test_string(self):
        assert "100 chars" in _auto_summary("x" * 100)
