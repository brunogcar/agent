"""Tests for the stats action.
v1.2: Added collections validation test.
"""
from __future__ import annotations

from tools.memory import memory

class TestStatsSuccess:
    def test_stats_returns_counts(self, mock_cfg, mock_store):
        result = memory(action="stats")
        assert result["status"] == "success"
        assert "collections" in result["data"]
        assert "total" in result["data"]
        assert result["data"]["total"] == 35  # 10+20+5 from mock_store

class TestStatsValidation:
    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        """v1.2: stats must reject empty collections list."""
        result = memory(action="stats", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]
