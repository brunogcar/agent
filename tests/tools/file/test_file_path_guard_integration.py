"""Test that file_ops actions properly integrate with core.path_guard.

These tests verify that the file tool uses the centralized path_guard for:
  - Path resolution (symlink safety, root scoping)
  - Protected file checks (WRITE_OPERATIONS classification)
  - Error formatting (make_path_error)

This is a v1.1 addition — previously file_ops had its own _resolve() in helpers.py
that bypassed path_guard. These tests ensure that regression never happens.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch
from tools.file import file


class TestPathGuardIntegration:
    """Verify file tool delegates to core.path_guard correctly."""

    def test_write_file_uses_path_guard(self, mock_cfg, monkeypatch):
        """Verify write_file calls resolve_path via _safe_resolve (which now wraps path_guard)."""
        calls = []

        # Get the CURRENT resolve_path (which is the conftest mock)
        import core.path_guard as _pg
        current_resolve = _pg.resolve_path

        def tracking_resolve(path, default_root="agent", require_exists=False):
            calls.append((str(path), default_root, require_exists))
            # Call the conftest's mock resolve_path, NOT the real one
            return current_resolve(path, default_root, require_exists)

        monkeypatch.setattr("core.path_guard.resolve_path", tracking_resolve)
        monkeypatch.setattr("tools.file.resolve_path", tracking_resolve)

        path = str(mock_cfg.workspace_root / "test.txt")
        file(action="write_file", path=path, content="test")

        # Should have been called at least once for path resolution
        assert len(calls) > 0
        assert any("test.txt" in str(c[0]) for c in calls)

    def test_null_bytes_blocked(self, mock_cfg):
        """Null bytes in path should be rejected by path_guard."""
        result = file(action="write_file", path="test\x00.txt", content="x")
        assert result["status"] == "error"
        assert "null" in result["error"].lower() or "invalid" in result["error"].lower()

    def test_traversal_blocked(self, mock_cfg):
        """Path traversal outside agent_root should be blocked."""
        result = file(action="write_file", path="../../outside.txt", content="x")
        assert result["status"] == "error"
        assert "outside" in result["error"].lower()

    def test_protected_file_blocked_via_path_guard(self, mock_cfg, monkeypatch):
        """Write to protected file should be blocked by check_protected_file."""
        def always_block(path, operation):
            return False, "Blocked by path_guard test"

        monkeypatch.setattr("core.path_guard.check_protected_file", always_block)
        monkeypatch.setattr("tools.file.check_protected_file", always_block)

        path = str(mock_cfg.workspace_root / "anything.txt")
        result = file(action="write_file", path=path, content="x")
        assert result["status"] == "error"
        assert "Blocked by path_guard test" in result["error"]

    def test_move_file_protected_destination(self, mock_cfg, monkeypatch):
        """move_file to a protected destination should be blocked."""
        def block_destination(path, operation):
            p_str = str(path).replace("\\", "/")
            if "dest" in p_str and operation == "move_file":
                return False, "Destination is protected"
            return True, ""

        monkeypatch.setattr("core.path_guard.check_protected_file", block_destination)
        monkeypatch.setattr("tools.file.check_protected_file", block_destination)

        src = mock_cfg.workspace_root / "src.txt"
        src.write_text("x", encoding="utf-8")
        dst = str(mock_cfg.workspace_root / "dest.txt")

        result = file(action="move_file", source=str(src), destination=dst)
        assert result["status"] == "error"
        assert "protected" in result["error"].lower()

    def test_copy_file_protected_destination(self, mock_cfg, monkeypatch):
        """copy_file to a protected destination should be blocked."""
        def block_destination(path, operation):
            p_str = str(path).replace("\\", "/")
            if "dest" in p_str and operation == "copy_file":
                return False, "Destination is protected"
            return True, ""

        monkeypatch.setattr("core.path_guard.check_protected_file", block_destination)
        monkeypatch.setattr("tools.file.check_protected_file", block_destination)

        src = mock_cfg.workspace_root / "src.txt"
        src.write_text("x", encoding="utf-8")
        dst = str(mock_cfg.workspace_root / "dest.txt")

        result = file(action="copy_file", source=str(src), destination=dst)
        assert result["status"] == "error"
        assert "protected" in result["error"].lower()
