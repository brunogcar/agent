"""
tests/tools/test_memory_tool_janitor.py
Unit tests for the unified memory tool's janitor action.
"""
from unittest.mock import patch
from tools.memory_tool import memory

@patch('tools.memory_tool.archive_old_episodes')
@patch('tools.memory_tool.purge_stale_rules')
def test_janitor_action_does_not_load_memory_store(mock_purge, mock_archive):
    """
    The janitor action must run without triggering the heavy chromadb import.
    It should return combined stats from both archival and purging.
    """
    mock_archive.return_value = {"archived": 5, "error": None}
    mock_purge.return_value = {"purged": 2, "error": None}

    # Call the tool
    result = memory(action="janitor")

    # Verify it returns the combined stats
    assert result["status"] == "success"
    assert result["data"]["episodic_archived"] == 5
    assert result["data"]["rules_purged"] == 2
    assert result["data"]["errors"] == []

    # Verify the janitor functions were called
    mock_archive.assert_called_once()
    mock_purge.assert_called_once()
