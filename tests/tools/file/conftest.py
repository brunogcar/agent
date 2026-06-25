"""Shared fixtures for file tool tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path for isolation."""
    test_root = tmp_path / "pytest_test_root"
    test_root.mkdir(parents=True, exist_ok=True)

    mock = MagicMock()
    mock.agent_root = test_root / "agent"
    mock.workspace_root = test_root / "workspace"
    mock.workspace_index = test_root / "index"
    mock.agent_root.mkdir(parents=True, exist_ok=True)
    mock.workspace_root.mkdir(parents=True, exist_ok=True)
    mock.workspace_index.mkdir(parents=True, exist_ok=True)

    # Create a simple is_protected that protects nothing in tests
    def _is_protected(p):
        return False
    mock.is_protected = _is_protected

    monkeypatch.setattr("core.config.cfg", mock)
    monkeypatch.setattr("core.path_guard.cfg", mock)
    monkeypatch.setattr("tools.file_ops.helpers.cfg", mock)
    monkeypatch.setattr("tools.file_ops.helpers._ALLOWED_ROOTS", None)

    # Patch path_guard resolve_path to use our mock roots
    # CRITICAL: Must patch tools.file.resolve_path because facade imports it at module level
    def _resolve_path(path_str, default_root="agent", require_exists=False):
        from pathlib import Path as _Path
        p = _Path(path_str)
        if not p.is_absolute():
            root = mock.agent_root if default_root == "agent" else mock.workspace_root
            p = root / p
        resolved = p.resolve()
        for root in [mock.agent_root, mock.workspace_root]:
            try:
                resolved.relative_to(root)
                return resolved, ""
            except ValueError:
                continue
        return None, f"Path outside allowed roots"

    # Patch BOTH the module attribute AND the facade's imported reference
    monkeypatch.setattr("core.path_guard.resolve_path", _resolve_path)
    monkeypatch.setattr("tools.file.resolve_path", _resolve_path)

    # Also patch make_path_error to return clean error dicts
    def _make_path_error(path, operation, error, trace_id=""):
        return {"status": "error", "error": error, "path": str(path), "operation": operation, "trace_id": trace_id}
    monkeypatch.setattr("core.path_guard.make_path_error", _make_path_error)
    monkeypatch.setattr("tools.file.make_path_error", _make_path_error)

    yield mock

    # Cleanup after test
    import shutil
    try:
        shutil.rmtree(test_root, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def sample_txt(mock_cfg):
    """Create a sample text file."""
    path = mock_cfg.workspace_root / "sample.txt"
    path.write_text("Hello World\nLine 2\nLine 3\nLine 4\nLine 5", encoding="utf-8")
    return str(path)


@pytest.fixture
def sample_dir(mock_cfg):
    """Create a sample directory with files."""
    d = mock_cfg.workspace_root / "testdir"
    d.mkdir(parents=True, exist_ok=True)
    (d / "a.txt").write_text("a", encoding="utf-8")
    (d / "b.txt").write_text("b", encoding="utf-8")
    sub = d / "subdir"
    sub.mkdir()
    (sub / "c.txt").write_text("c", encoding="utf-8")
    return str(d)
