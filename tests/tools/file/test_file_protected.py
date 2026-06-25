"""Test protected file enforcement."""

from __future__ import annotations

import pytest
from pathlib import Path
from tools.file import file


class TestProtectedFiles:
    def test_write_file_protected(self, mock_cfg, monkeypatch):
        def _is_protected(p):
            return Path(p).name == "server.py"
        monkeypatch.setattr("core.config.cfg.is_protected", _is_protected)

        path = str(mock_cfg.workspace_root / "server.py")
        result = file(action="write_file", path=path, content="hack")
        assert result.get("status") == "error"
        assert "protected" in result.get("error", "").lower()

    def test_delete_file_protected(self, mock_cfg, monkeypatch):
        def _is_protected(p):
            return Path(p).name == "server.py"
        monkeypatch.setattr("core.config.cfg.is_protected", _is_protected)

        p = mock_cfg.workspace_root / "server.py"
        p.write_text("x", encoding="utf-8")

        result = file(action="delete_file", path=str(p), force=True)
        assert result.get("status") == "error"
        assert "protected" in result.get("error", "").lower()

    def test_move_file_protected_source(self, mock_cfg, monkeypatch):
        def _is_protected(p):
            return Path(p).name == "server.py"
        monkeypatch.setattr("core.config.cfg.is_protected", _is_protected)

        src = mock_cfg.workspace_root / "server.py"
        src.write_text("x", encoding="utf-8")
        dst = mock_cfg.workspace_root / "moved.py"

        result = file(action="move_file", source=str(src), destination=str(dst))
        assert result.get("status") == "error"
        assert "protected" in result.get("error", "").lower()

    def test_edit_file_protected(self, mock_cfg, monkeypatch):
        def _is_protected(p):
            return Path(p).name == "server.py"
        monkeypatch.setattr("core.config.cfg.is_protected", _is_protected)

        p = mock_cfg.workspace_root / "server.py"
        p.write_text("def old(): pass", encoding="utf-8")

        result = file(
            action="edit_file",
            path=str(p),
            edits=[{"oldText": "def old():", "newText": "def new():"}],
        )
        assert result.get("status") == "error"
        assert "protected" in result.get("error", "").lower()

    def test_patch_file_protected(self, mock_cfg, monkeypatch):
        def _is_protected(p):
            return Path(p).name == "server.py"
        monkeypatch.setattr("core.config.cfg.is_protected", _is_protected)

        p = mock_cfg.workspace_root / "server.py"
        p.write_text("def old(): pass", encoding="utf-8")

        result = file(
            action="patch_file",
            path=str(p),
            old="def old():",
            new="def new():",
        )
        assert result.get("status") == "error"
        assert "protected" in result.get("error", "").lower()
