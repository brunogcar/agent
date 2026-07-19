"""tests/workflows/autocode/test_helpers.py
Tests for autocode helper functions — path helpers, patch application,
file-context helpers, and _call() trace_id propagation.

[v1.2 P1] The former test_call_trace_id.py was merged into this file (it had
only 1 parametrized test class with 6 cases — too small to warrant its own
file, and the function it tests — `_call()` — lives in helpers.py).
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch


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


# ── [v1.2 P1] _call() trace_id propagation ────────────────────────────────────
# Merged from the former test_call_trace_id.py (1 parametrized test class, 6
# cases). Each _call() caller must pass trace_id=tid so retry-exhaustion errors
# are attributed to the workflow's trace. Before v1.2, the trace_id param
# existed on _call() but no caller passed it — errors used trace_id="".


def _trace_test_base_state():
    """Local minimal state for trace_id propagation tests.

    Mirrors the conftest base_state fixture but uses a string project_root
    (the original test_call_trace_id.py behavior) — these tests don't write
    files, they only mock _call() and inspect its kwargs.
    """
    from workflows.autocode_impl.state import _default_state
    state = _default_state(task="test task")
    state["trace_id"] = "test-trace-001"
    state["task_type"] = "feature"
    state["project_root"] = "/tmp"
    state["plan_state"]["plan"] = [{"id": 1, "label": "write_code", "description": "implement"}]
    state["plan_state"]["current_step"] = 0
    state["tdd"]["max_retries"] = 3
    return state


class TestCallTraceIdPropagation:
    """Each _call() caller must pass trace_id=tid.

    [v1.2 P1] All 6 _call() callers must pass trace_id=tid so retry-exhaustion
    errors are attributed to the workflow's trace. Before v1.2, the trace_id
    param existed on _call() but no caller passed it — errors used trace_id="".
    """

    @pytest.mark.parametrize("node_module,node_func,state_overrides", [
        ("workflows.autocode_impl.nodes.classify", "node_classify_task", {}),
        ("workflows.autocode_impl.nodes.brainstorm", "node_brainstorm", {"task_type": "feature"}),
        ("workflows.autocode_impl.nodes.plan", "node_write_plan", {}),
        # [v1.2 fix] node_write_tests requires the current plan step's label to
        # be "write_tests" (else it early-returns and never calls _call). The
        # default base_state's plan has label "write_code", so override.
        ("workflows.autocode_impl.nodes.tests", "node_write_tests", {
            "plan_state": {
                "plan": [{"id": 1, "label": "write_tests", "description": "write tests",
                          "acceptance": "tests exist", "files": []}],
                "current_step": 0,
                "spec": "test spec",
                "brainstorm_notes": "",
                "plan_accepted": False,
            },
        }),
        ("workflows.autocode_impl.nodes.execute", "node_execute_step", {}),
        ("workflows.autocode_impl.nodes.llm_review", "node_llm_review", {}),
    ])
    def test_call_passes_trace_id(self, node_module, node_func, state_overrides, tmp_path):
        """Mock _call() and assert it receives trace_id matching state's trace_id."""
        state = _trace_test_base_state()
        state["project_root"] = str(tmp_path)
        state.update(state_overrides)

        import importlib
        mod = importlib.import_module(node_module)
        func = getattr(mod, node_func)

        with patch(f"{node_module}._call") as mock_call:
            mock_call.return_value = '{"task_type": "feature", "questions": [], "steps": [], "test_code": "", "code": "", "verdict": "pass", "issues": []}'
            try:
                func(state)
            except Exception:
                pass  # We only care about the _call() kwargs
            assert mock_call.called, f"{node_func} did not call _call()"
            _, kwargs = mock_call.call_args
            assert kwargs.get("trace_id") == state["trace_id"], \
                f"{node_func} did not pass trace_id=tid to _call() (got trace_id={kwargs.get('trace_id')!r})"
