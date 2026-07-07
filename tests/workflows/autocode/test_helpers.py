"""tests/workflows/autocode/test_helpers.py
Tests for autocode helper functions — path helpers, patch application,
and file-context helpers.
"""
from __future__ import annotations

import pytest
from pathlib import Path


class TestAutocodePathHelpers:
    def test_get_autocode_run_path_creates_directory(self, temp_workspace):
        from workflows.autocode_impl.helpers import _get_autocode_run_path
        run_dir = _get_autocode_run_path("test-trace-123")
        assert run_dir.exists()
        assert run_dir.name == "test-trace-123"
        assert run_dir.parent.parent.name == "autocode"

    def test_cleanup_old_runs_removes_stale(self, temp_workspace, monkeypatch):
        from workflows.autocode_impl.helpers import _cleanup_old_autocode_runs
        from datetime import datetime, timedelta
        import core.tracer
        monkeypatch.setattr(core.tracer.tracer, "step", lambda *a, **kw: None)

        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        old_dir = temp_workspace / "autocode" / old_date / "old-trace"
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "test.py").write_text("pass")

        recent_date = datetime.now().strftime("%Y%m%d")
        recent_dir = temp_workspace / "autocode" / recent_date / "recent-trace"
        recent_dir.mkdir(parents=True, exist_ok=True)
        (recent_dir / "test.py").write_text("pass")

        _cleanup_old_autocode_runs(max_age_days=7)
        assert not old_dir.exists()
        assert recent_dir.exists()


class TestApplyPatch:
    def test_success_no_bak(self, temp_workspace):
        """[Bug #1] Successful patch must not create .bak files."""
        from workflows.autocode_impl.patch import apply_patch
        target = temp_workspace / "target.py"
        target.write_text("def old(): pass\n", encoding="utf-8")
        result = apply_patch(target, old="def old(): pass\n", new="def new(): return True\n")
        assert result.ok is True
        assert "def new():" in target.read_text()
        assert not target.with_suffix(".py.bak").exists()

    def test_patches_no_bak(self, temp_workspace):
        """[Bug #1] Patch array must not create .bak files."""
        from workflows.autocode_impl.patch import apply_patch
        target = temp_workspace / "multi.py"
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")
        result = apply_patch(target, old="a = 1", new="a = 2")
        assert result.ok is True
        assert not target.with_suffix(".py.bak").exists()

    def test_fallback_on_mismatch(self, temp_workspace):
        """Mismatched old_text must return ok=False without corrupting file."""
        from workflows.autocode_impl.patch import apply_patch
        target = temp_workspace / "fallback.py"
        target.write_text("original content", encoding="utf-8")
        fail = apply_patch(target, old="nonexistent", new="replacement")
        assert fail.ok is False
        assert target.read_text() == "original content"


class TestProtectedPathResolution:
    def test_protected_path_resolves_against_project_root(self, temp_workspace):
        from core.config import cfg
        (temp_workspace / "core").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "core" / "config.py").touch()
        (temp_workspace / "server.py").touch()
        (temp_workspace / "workspace").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "workspace" / "output.py").touch()
        assert cfg.is_protected(temp_workspace / "core" / "config.py")
        assert cfg.is_protected(temp_workspace / "server.py")
        assert not cfg.is_protected(temp_workspace / "workspace" / "output.py")


class TestPathTraversal:
    def test_absolute_path_blocked(self, temp_workspace):
        """[P1 #11] Absolute paths must be blocked."""
        from workflows.autocode_impl.nodes.validate import node_validate_input
        state = {
            "task": "test", "trace_id": "t1", "status": "running",
            "task_type": "feature", "project_root": str(temp_workspace),
            "files": {"/etc/passwd": "content"},
        }
        result = node_validate_input(state)
        assert result.get("status") == "error" or "error" in result

    def test_windows_absolute_blocked(self, temp_workspace):
        from workflows.autocode_impl.nodes.validate import node_validate_input
        state = {
            "task": "test", "trace_id": "t1", "status": "running",
            "task_type": "feature", "project_root": str(temp_workspace),
            "files": {"C:\\Windows\\system32\\x": "content"},
        }
        result = node_validate_input(state)
        assert result.get("status") == "error" or "error" in result

    def test_url_encoded_traversal_blocked(self, temp_workspace):
        from workflows.autocode_impl.nodes.validate import node_validate_input
        state = {
            "task": "test", "trace_id": "t1", "status": "running",
            "task_type": "feature", "project_root": str(temp_workspace),
            "files": {"%2e%2e%2fsecret": "content"},
        }
        result = node_validate_input(state)
        assert result.get("status") == "error" or "error" in result

    def test_relative_traversal_to_protected_blocked(self, temp_workspace):
        from workflows.autocode_impl.nodes.validate import node_validate_input
        (temp_workspace / "core").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "core" / "config.py").touch()
        state = {
            "task": "test", "trace_id": "t1", "status": "running",
            "task_type": "feature", "project_root": str(temp_workspace),
            "files": {"../core/config.py": "malicious"},
        }
        result = node_validate_input(state)
        assert result.get("status") == "error" or "error" in result
