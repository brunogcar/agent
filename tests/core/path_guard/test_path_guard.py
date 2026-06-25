"""tests/core/path_guard/test_path_guard.py

Comprehensive unit tests for the centralized path guard.
Uses pytest's tmp_path fixture for cross-platform (Windows/Linux) filesystem safety.

v1.1 additions:
  - Tests for move_file, copy_file, create_directory in WRITE_OPERATIONS
  - Tests for check_git_operation without silent fallback on missing cwd
  - Tests for clone action scoping (workspace-only)
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.path_guard import (
    resolve_path,
    check_protected_file,
    check_git_operation,
    make_path_error,
    _is_within,
    WRITE_OPERATIONS,
    READ_OPERATIONS,
    GIT_WORKSPACE_ONLY,
)

# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def mock_config(tmp_path):
    """
    Mock config with real, temporary paths.
    Using tmp_path ensures Path.resolve() and symlinks work correctly on Windows.
    """
    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    workspace_root = agent_root / "workspace"
    workspace_root.mkdir()

    # Create dummy protected files
    core_dir = agent_root / "core"
    core_dir.mkdir()
    (core_dir / "config.py").touch()
    (core_dir / "llm.py").touch()

    with patch("core.path_guard.cfg") as mock_cfg:
        mock_cfg.agent_root = agent_root
        mock_cfg.workspace_root = workspace_root

        # Mock the is_protected method from core.config
        def is_protected_side_effect(p):
            # Match if the path ends with core/config.py or core/llm.py
            p_str = str(p).replace("\\", "/")
            return p_str.endswith("core/config.py") or p_str.endswith("core/llm.py")

        mock_cfg.is_protected = MagicMock(side_effect=is_protected_side_effect)
        yield mock_cfg

# =============================================================================
# Test _is_within
# =============================================================================
class TestIsWithin:
    def test_child_within_parent(self, mock_config):
        parent = mock_config.agent_root
        child = parent / "tools" / "file.py"
        assert _is_within(child, parent) is True

    def test_child_outside_parent(self, mock_config, tmp_path):
        parent = mock_config.agent_root
        child = tmp_path / "other" / "file.py"
        assert _is_within(child, parent) is False

    def test_same_path(self, mock_config):
        parent = mock_config.agent_root
        assert _is_within(parent, parent) is True

    @pytest.mark.skipif(os.name == 'nt', reason="Symlink creation requires admin on Windows")
    def test_symlink_within(self, mock_config, tmp_path):
        target = tmp_path / "real"
        link = tmp_path / "link"
        target.touch()
        link.symlink_to(target)
        assert _is_within(link, tmp_path) is True

    @pytest.mark.skipif(os.name == 'nt', reason="Symlink creation requires admin on Windows")
    def test_symlink_outside(self, mock_config, tmp_path):
        """
        Symlink physically inside agent_root but pointing outside.
        _is_within() follows the symlink via Path.resolve(), so it should detect the escape.
        """
        outside = tmp_path / "outside"
        outside.touch()
        link = mock_config.agent_root / "link"
        link.symlink_to(outside)
        # The symlink resolves to 'outside', which is NOT within agent_root
        assert _is_within(link, mock_config.agent_root) is False

# =============================================================================
# Test resolve_path
# =============================================================================
class TestResolvePath:
    def test_relative_path_defaults_to_agent(self, mock_config):
        resolved, err = resolve_path("tools/file.py", default_root="agent")
        assert err == ""
        assert resolved == (mock_config.agent_root / "tools/file.py").resolve()

    def test_absolute_path_outside_agent_blocked(self, mock_config, tmp_path):
        outside = tmp_path / "outside" / "file.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.touch()

        resolved, err = resolve_path(str(outside))
        assert resolved is None
        assert "outside AGENT_ROOT" in err

    def test_traversal_blocked(self, mock_config):
        resolved, err = resolve_path("../../etc/passwd")
        assert resolved is None
        assert "outside AGENT_ROOT" in err

    def test_empty_path(self, mock_config):
        resolved, err = resolve_path("")
        assert resolved is None
        assert "empty" in err.lower()

    def test_null_bytes(self, mock_config):
        path = "file.py\x00"
        resolved, err = resolve_path(path)
        assert resolved is None
        assert "null" in err.lower() or "Invalid" in err

# =============================================================================
# Test check_protected_file
# =============================================================================
class TestCheckProtectedFile:
    def test_read_protected_allowed(self, mock_config):
        path = "core/config.py"
        allowed, err = check_protected_file(path, "read")
        assert allowed is True
        assert err == ""

    def test_write_protected_blocked(self, mock_config):
        path = "core/config.py"
        allowed, err = check_protected_file(path, "write")
        assert allowed is False
        assert "protected" in err.lower()

    def test_write_unprotected_allowed(self, mock_config):
        path = "tools/file.py"
        allowed, err = check_protected_file(path, "write")
        assert allowed is True

    # v1.1: Test new write operations are in WRITE_OPERATIONS
    def test_move_file_in_write_operations(self):
        assert "move_file" in WRITE_OPERATIONS

    def test_copy_file_in_write_operations(self):
        assert "copy_file" in WRITE_OPERATIONS

    def test_create_directory_in_write_operations(self):
        assert "create_directory" in WRITE_OPERATIONS

    def test_move_file_protected_blocked(self, mock_config):
        path = "core/config.py"
        allowed, err = check_protected_file(path, "move_file")
        assert allowed is False
        assert "protected" in err.lower()

    def test_copy_file_protected_blocked(self, mock_config):
        path = "core/config.py"
        allowed, err = check_protected_file(path, "copy_file")
        assert allowed is False
        assert "protected" in err.lower()

    # v1.1: Test read operations include new actions
    def test_list_allowed_directories_in_read_operations(self):
        assert "list_allowed_directories" in READ_OPERATIONS

# =============================================================================
# Test check_git_operation
# =============================================================================
class TestCheckGitOperation:
    def test_clone_in_workspace_allowed(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "clone",
            cwd=str(mock_config.workspace_root)
        )
        assert allowed is True
        assert err == ""

    def test_clone_in_agent_root_blocked(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "clone",
            cwd=str(mock_config.agent_root)
        )
        assert allowed is False
        assert "WORKSPACE_ROOT" in err

    def test_init_in_workspace_allowed(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "init",
            cwd=str(mock_config.workspace_root)
        )
        assert allowed is True

    def test_init_in_agent_root_blocked(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "init",
            cwd=str(mock_config.agent_root)
        )
        assert allowed is False
        assert "WORKSPACE_ROOT" in err

    def test_diff_in_agent_allowed(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "diff",
            cwd=str(mock_config.agent_root)
        )
        assert allowed is True

    # v1.1: Removed test_clone_with_target_outside_workspace because
    # check_git_operation no longer validates target for clone. Target is a
    # remote URL, not a filesystem path. Destination validation happens in the handler.

    # v1.1: Test that missing cwd fails fast (no silent fallback)
    def test_missing_cwd_fails_fast(self, mock_config):
        allowed, err, cwd = check_git_operation(
            "status",
            cwd="nonexistent_path_12345"
        )
        assert allowed is False
        assert err != ""
        assert cwd is None

    # v1.1: Verify clone is in GIT_WORKSPACE_ONLY
    def test_clone_in_git_workspace_only(self):
        assert "clone" in GIT_WORKSPACE_ONLY

# =============================================================================
# Test make_path_error
# =============================================================================
class TestMakePathError:
    def test_basic_error(self):
        err = make_path_error("/bad/path", "read", "Outside root")
        assert err["status"] == "error"
        assert "Outside root" in err["error"]
        assert err["path"] == "/bad/path"
        assert "trace_id" in err

    def test_error_with_suggestion(self):
        err = make_path_error(
            "/etc/passwd",
            "read",
            "Outside root",
            suggestion="Use paths relative to agent root"
        )
        assert "Suggestion: Use paths relative to agent root" in err["error"]
