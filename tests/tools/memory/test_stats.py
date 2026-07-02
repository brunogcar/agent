"""Tests for the stats action."""
from __future__ import annotations

from tools.memory import memory


class TestStatsSuccess:
    def test_stats(self, mock_cfg, mock_store):
        result = memory(action="stats")
        assert result["status"] == "success"
        assert result["data"]["total"] == 35  # 10 + 20 + 5
        assert "episodic" in result["data"]["collections"]
        assert "semantic" in result["data"]["collections"]
        assert "procedural" in result["data"]["collections"]
        mock_store.stats.assert_called_once()
