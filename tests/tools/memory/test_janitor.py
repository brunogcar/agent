"""Tests for the janitor action — critical bypass test.

The janitor action must NEVER call _mem() or trigger ChromaDB import.
This is the most important regression guard in the memory test suite.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.memory import memory


class TestJanitorBypass:
    def test_janitor_never_calls_mem(self, mock_cfg):
        """[CRITICAL] Janitor must bypass ChromaDB initialization entirely."""
        with patch("tools.memory_ops.helpers._mem") as mock_mem:
            with patch("tools.memory_ops.actions.janitor.archive_old_episodes") as mock_archive:
                with patch("tools.memory_ops.actions.janitor.purge_stale_rules") as mock_purge:
                    mock_archive.return_value = {"archived": 5, "error": None}
                    mock_purge.return_value = {"purged": 2, "error": None}

                    result = memory(action="janitor")

                    mock_mem.assert_not_called()
                    assert result["status"] == "success"
                    assert result["data"]["episodic_archived"] == 5
                    assert result["data"]["rules_purged"] == 2

    def test_janitor_with_errors(self, mock_cfg):
        """Janitor should collect errors from both functions."""
        with patch("tools.memory_ops.actions.janitor.archive_old_episodes") as mock_archive:
            with patch("tools.memory_ops.actions.janitor.purge_stale_rules") as mock_purge:
                mock_archive.return_value = {"archived": 0, "error": "archive failed"}
                mock_purge.return_value = {"purged": 0, "error": "purge failed"}

                result = memory(action="janitor")

                assert result["status"] == "success"
                assert len(result["data"]["errors"]) == 2
                assert "archive failed" in result["data"]["errors"]
                assert "purge failed" in result["data"]["errors"]

    def test_janitor_no_errors(self, mock_cfg):
        """Janitor with clean run returns empty errors list."""
        with patch("tools.memory_ops.actions.janitor.archive_old_episodes") as mock_archive:
            with patch("tools.memory_ops.actions.janitor.purge_stale_rules") as mock_purge:
                mock_archive.return_value = {"archived": 3, "error": None}
                mock_purge.return_value = {"purged": 1, "error": None}

                result = memory(action="janitor")

                assert result["data"]["errors"] == []
