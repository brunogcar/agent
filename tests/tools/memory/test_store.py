"""Tests for the store action."""
from __future__ import annotations

import pytest

from tools.memory import memory


class TestStoreValidation:
    def test_missing_text_error(self, mock_cfg, mock_store):
        result = memory(action="store", text="")
        assert result["status"] == "error"
        assert "text is required" in result["error"]

    def test_invalid_importance_error(self, mock_cfg, mock_store):
        result = memory(action="store", text="test", importance=15)
        assert result["status"] == "error"
        assert "importance must be 1-10" in result["error"]

    def test_text_too_large_error(self, mock_cfg, mock_store):
        """P2: Centralized cfg.memory_max_entry_bytes enforcement."""
        huge_text = "x" * 60000  # 60KB, exceeds 50KB limit
        result = memory(action="store", text=huge_text)
        assert result["status"] == "error"
        assert "exceeds" in result["error"]
        assert "50000" in result["error"]

    def test_invalid_tags_error(self, mock_cfg, mock_store):
        result = memory(action="store", text="test", tags="bad<tag")
        assert result["status"] == "error"
        assert "cannot contain" in result["error"]

    def test_invalid_memory_type_rejected(self, mock_cfg, mock_store):
        """Fail-fast: invalid memory_type must not silently default to semantic."""
        result = memory(action="store", text="test", memory_type="invalid_type")
        assert result["status"] == "error"
        assert "Invalid memory_type" in result["error"]
        assert "episodic" in result["error"]
        assert "semantic" in result["error"]
        assert "procedural" in result["error"]

    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        """Empty collections list is ambiguous — reject it."""
        result = memory(action="store", text="test", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]


class TestStoreSuccess:
    def test_successful_store(self, mock_cfg, mock_store):
        result = memory(
            action="store",
            text="A useful fact",
            memory_type="semantic",
            importance=7,
            tags="test,fact",
        )
        assert result["status"] == "success"
        mock_store.store.assert_called_once()

    def test_store_episodic(self, mock_cfg, mock_store):
        result = memory(
            action="store",
            text="Fixed a bug",
            memory_type="episodic",
            importance=8,
            goal="fix bug",
            outcome="success",
        )
        assert result["status"] == "success"
        call_kwargs = mock_store.store.call_args.kwargs
        assert call_kwargs["memory_type"] == "episodic"

    def test_store_procedural(self, mock_cfg, mock_store):
        result = memory(
            action="store",
            text="Check line N-2 for unclosed brackets",
            memory_type="procedural",
            importance=9,
        )
        assert result["status"] == "success"
        call_kwargs = mock_store.store.call_args.kwargs
        assert call_kwargs["memory_type"] == "procedural"

    def test_trace_id_passed_to_store(self, mock_cfg, mock_store):
        memory(action="store", text="test", trace_id="abc123")
        call_kwargs = mock_store.store.call_args.kwargs
        assert call_kwargs["trace_id"] == "abc123"


class TestConfigIntegration:
    def test_memory_limit_uses_config(self, mock_cfg, mock_store):
        """Verify the error message dynamically uses cfg.memory_max_entry_bytes."""
        mock_cfg.memory_max_entry_bytes = 100  # Tiny limit for test
        huge_text = "x" * 200
        result = memory(action="store", text=huge_text)
        assert result["status"] == "error"
        assert "100" in result["error"]
