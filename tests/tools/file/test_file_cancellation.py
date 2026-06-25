"""Test cancellation guard prevents file mutations."""

from __future__ import annotations

import asyncio
import pytest
from pathlib import Path
from tools.file import file


class TestCancellationGuard:
    def test_write_file_cancelled(self, mock_cfg, monkeypatch):
        def _ensure_not_cancelled(tid=""):
            raise asyncio.CancelledError("Workflow cancelled")
        monkeypatch.setattr("core.runtime.cancellation.ensure_not_cancelled", _ensure_not_cancelled)

        path = str(mock_cfg.workspace_root / "cancelled.txt")
        result = file(action="write_file", path=path, content="should not write")
        assert result.get("status") == "error"
        assert not Path(path).exists()

    def test_delete_file_cancelled(self, mock_cfg, monkeypatch):
        def _ensure_not_cancelled(tid=""):
            raise asyncio.CancelledError("Workflow cancelled")
        monkeypatch.setattr("core.runtime.cancellation.ensure_not_cancelled", _ensure_not_cancelled)

        p = mock_cfg.workspace_root / "to_delete.txt"
        p.write_text("x", encoding="utf-8")

        result = file(action="delete_file", path=str(p), force=True)
        assert result.get("status") == "error"
        assert Path(p).exists()  # File NOT deleted

    def test_move_file_cancelled(self, mock_cfg, monkeypatch):
        def _ensure_not_cancelled(tid=""):
            raise asyncio.CancelledError("Workflow cancelled")
        monkeypatch.setattr("core.runtime.cancellation.ensure_not_cancelled", _ensure_not_cancelled)

        src = mock_cfg.workspace_root / "src.txt"
        src.write_text("x", encoding="utf-8")
        dst = mock_cfg.workspace_root / "dst.txt"

        result = file(action="move_file", source=str(src), destination=str(dst))
        assert result.get("status") == "error"
        assert Path(src).exists()  # Source NOT moved
        assert not Path(dst).exists()  # Destination NOT created

    def test_edit_file_cancelled(self, mock_cfg, monkeypatch):
        def _ensure_not_cancelled(tid=""):
            raise asyncio.CancelledError("Workflow cancelled")
        monkeypatch.setattr("core.runtime.cancellation.ensure_not_cancelled", _ensure_not_cancelled)

        p = mock_cfg.workspace_root / "to_edit.txt"
        p.write_text("original", encoding="utf-8")

        result = file(
            action="edit_file",
            path=str(p),
            edits=[{"oldText": "original", "newText": "modified"}],
        )
        assert result.get("status") == "error"
        assert Path(p).read_text(encoding="utf-8") == "original"  # NOT modified

    def test_patch_file_cancelled(self, mock_cfg, monkeypatch):
        def _ensure_not_cancelled(tid=""):
            raise asyncio.CancelledError("Workflow cancelled")
        monkeypatch.setattr("core.runtime.cancellation.ensure_not_cancelled", _ensure_not_cancelled)

        p = mock_cfg.workspace_root / "to_patch.txt"
        p.write_text("def old(): pass", encoding="utf-8")

        result = file(
            action="patch_file",
            path=str(p),
            old="def old():",
            new="def new():",
        )
        assert result.get("status") == "error"
        assert "def old():" in Path(p).read_text(encoding="utf-8")  # NOT patched
