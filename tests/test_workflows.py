"""
tests/test_workflows.py -- Unit tests for workflow state and routing
Run from D:/mcp/agent/:
pytest tests/test_workflows.py -v

Tests:
  - WorkflowState TypedDict structure
  - node_done sets status=success
  - node_error sets status=failed with non-empty message
  - Autocode routing logic (Updated for split architecture)
  - Protected file check in config
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── WorkflowState helpers ─────────────────────────────────────────────────────

def test_node_done_sets_success():
    from workflows.base import node_done, WorkflowState
    state: WorkflowState = {
        "workflow": "test", "goal": "test goal",
        "trace_id": "", "status": "running",
        "error": "", "result": "", "artifacts": [], "retries": 0,
    }
    result = node_done(state, result="all done")
    assert result["status"] == "success"
    assert result["result"] == "all done"

def test_node_error_sets_failed():
    from workflows.base import node_error, WorkflowState
    state: WorkflowState = {
        "workflow": "test", "goal": "test",
        "trace_id": "", "status": "running",
        "error": "", "result": "", "artifacts": [], "retries": 0,
    }
    result = node_error(state, "test_node", "something went wrong")
    assert result["status"] == "failed"
    assert result["error"] == "something went wrong"

def test_node_error_never_empty_message():
    """node_error must produce a non-empty message even if called with ''."""
    from workflows.base import node_error, WorkflowState
    state: WorkflowState = {
        "workflow": "test", "goal": "test",
        "trace_id": "", "status": "running",
        "error": "", "result": "", "artifacts": [], "retries": 0,
    }
    result = node_error(state, "some_node", "")
    assert result["status"] == "failed"
    assert len(result["error"]) > 0, "error message must not be empty"

# ── Autocode routing logic (Updated for split architecture) ───────────────────

def test_route_after_verify_pass_commits():
    """Verification pass should route to commit."""
    from workflows.autocode_helpers.routes import route_after_verify
    state = {"verification_passed": True, "status": "running"}
    assert route_after_verify(state) == "node_commit"

def test_route_after_verify_fail_ends():
    """Verification fail should route to END."""
    from workflows.autocode_helpers.routes import route_after_verify
    state = {"verification_passed": False, "status": "failed"}
    assert route_after_verify(state) == "END"

def test_route_after_run_tests_pass_verify():
    """Tests passing should route to verification."""
    from workflows.autocode_helpers.routes import route_after_run_tests
    state = {"tdd_status": "passed", "test_results": {"success": True}}
    assert route_after_run_tests(state) == "node_verify"

def test_route_after_run_tests_fail_debug():
    """Tests failing should route to systematic debug."""
    from workflows.autocode_helpers.routes import route_after_run_tests
    state = {"tdd_status": "failed", "test_results": {"success": False}}
    assert route_after_run_tests(state) == "node_systematic_debug"

def test_route_after_write_files_tests():
    """After writing files, route to run_tests for TDD loop."""
    from workflows.autocode_helpers.routes import route_after_write_files
    state = {"status": "running", "files_map": {"test.py": "pass"}}
    assert route_after_write_files(state) == "node_run_tests"

# ── Protected files ───────────────────────────────────────────────────────────

def test_protected_files_set_contains_core():
    from core.config import cfg
    must_protect = {"server.py", "registry.py", "core/config.py", "core/tracer.py"}
    for f in must_protect:
        assert cfg.is_protected(f), f"{f} should be protected"

def test_protected_files_expanded_set():
    from core.config import cfg
    # Phase 2/3 expanded set
    assert cfg.is_protected("core/memory.py"), "core/memory.py should be protected"
    assert cfg.is_protected("core/gateway.py"), "core/gateway.py should be protected"
    assert cfg.is_protected("core/llm.py"), "core/llm.py should be protected"

def test_is_protected_rejects_workspace_files():
    from core.config import cfg
    assert not cfg.is_protected("workspace/output.py")
    assert not cfg.is_protected("skills/b3/skill.py")
    assert not cfg.is_protected("tools/web.py")

# ── Autocode Workflow Integration Tests ───────────────────────────────────────

def test_autocode_goal_to_task_conversion():
    """
    Test that autocode workflow properly converts goal -> task.
    This is the critical fix for run_workflow() to work with the autocode graph,
    which expects a 'task' key in state instead of 'goal'.
    """
    from workflows.base import run_workflow

    # Run autocode workflow via base.py dispatcher (as meta-tool does)
    result = run_workflow(
        workflow_type="autocode",
        goal="Add input validation to memory store",
        trace_id="test-autocode-integration",
    )

    # Should not crash - graph should build and invoke
    assert "status" in result, "Result must have status field"
    # Status can be anything (running/failed/success) as long as it doesn't crash
    assert result["status"] in ("success", "failed", "running"), \
        f"Invalid status: {result['status']}"

def test_autocode_workflow_with_target_file():
    """
    Test autocode workflow with target_file and mode kwargs.
    """
    from workflows.base import run_workflow
    result = run_workflow(
        workflow_type="autocode",
        goal="Fix error in core/memory.py: ValueError missing argument",
        trace_id="test-autocode-with-target",
        target_file="core/memory.py",
        mode="fix_error",
    )

    assert "status" in result
    assert result["status"] in ("success", "failed", "running")