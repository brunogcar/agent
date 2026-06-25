"""Shared fixtures for file tool tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

@pytest.fixture(autouse=True)
def mock_cfg(monkeypatch, tmp_path):
    """Redirect agent_root and workspace_root to tmp_path for isolation.

    v1.1: workspace_root is now a subfolder of agent_root, matching real config
    where WORKSPACE_ROOT = AGENT_ROOT / workspace. This ensures resolve_path
    correctly handles paths in both locations.
    """
    test_root = tmp_path / "pytest_test_root"
    test_root.mkdir(parents=True, exist_ok=True)

    mock = MagicMock()
    # v1.1: workspace is inside agent, matching real D:/mcp/agent/workspace
    mock.agent_root = test_root / "agent"
    mock.workspace_root = mock.agent_root / "workspace"
    mock.workspace_index = mock.workspace_root / "index"
    mock.agent_root.mkdir(parents=True, exist_ok=True)
    mock.workspace_root.mkdir(parents=True, exist_ok=True)
    mock.workspace_index.mkdir(parents=True, exist_ok=True)

    # Create a simple is_protected that protects nothing in tests
    def _is_protected(p):
        return False
    mock.is_protected = _is_protected

    monkeypatch.setattr("core.config.cfg", mock)
    monkeypatch.setattr("core.path_guard.cfg", mock)

    # Patch resolve_path for tests to handle both roots correctly.
    # The real resolve_path resolves from ONE default_root. Tests pass relative
    # paths that may need to land in either root. We intercept and route correctly.
    def _resolve_path(path_str, default_root="agent", require_exists=False):
        from pathlib import Path as _Path
        p = _Path(path_str)

        # Handle null bytes
        if "\x00" in str(path_str):
            return None, "Path contains null bytes"

        # Handle absolute paths: verify within agent_root (which contains workspace)
        if p.is_absolute():
            resolved = p.resolve()
            try:
                resolved.relative_to(mock.agent_root)
                if require_exists and not resolved.exists():
                    return None, f"Path does not exist: {resolved}"
                return resolved, ""
            except ValueError:
                return None, f"Path outside AGENT_ROOT"

        # Handle relative paths
        # For default_root="agent": try agent_root first, then workspace_root
        # For default_root="workspace": try workspace_root first, then agent_root
        if default_root == "agent":
            roots_to_try = [mock.agent_root, mock.workspace_root]
        else:
            roots_to_try = [mock.workspace_root, mock.agent_root]

        for root in roots_to_try:
            candidate = (root / p).resolve()
            # Verify it stays within agent_root
            try:
                candidate.relative_to(mock.agent_root)
            except ValueError:
                continue

            if require_exists:
                if candidate.exists():
                    return candidate, ""
                continue
            else:
                return candidate, ""

        if require_exists:
            return None, f"Path does not exist: {path_str}"

        # Fallback: use default_root
        root = mock.agent_root if default_root == "agent" else mock.workspace_root
        return (root / p).resolve(), ""

    monkeypatch.setattr("core.path_guard.resolve_path", _resolve_path)
    monkeypatch.setattr("tools.file.resolve_path", _resolve_path)

    # Patch make_path_error for clean test output
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
