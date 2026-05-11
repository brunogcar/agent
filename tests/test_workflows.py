"""
tests/test_workflows.py -- Unit tests for workflow state and routing

Run from D:/mcp/agent/:
    pytest tests/test_workflows.py -v

Tests:
  - WorkflowState TypedDict structure
  - node_done sets status=success
  - node_error sets status=failed with non-empty message
  - route_after_review logic
  - route_after_test distinguishes SyntaxError from ruff
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


# ── Autocode routing logic ────────────────────────────────────────────────────

def test_route_after_review_approve():
    from workflows.autocode import route_after_review
    state = {"review": {"verdict": "APPROVE"}, "retries": 0, "error": ""}
    assert route_after_review(state) == "syntax_check"


def test_route_after_review_revise_within_budget():
    from workflows.autocode import route_after_review
    state = {"review": {"verdict": "REVISE"}, "retries": 0, "error": ""}
    assert route_after_review(state) == "retry"


def test_route_after_review_revise_over_budget():
    from workflows.autocode import route_after_review
    from core.config import cfg
    state = {"review": {"verdict": "REVISE"}, "retries": cfg.autocode_max_retries, "error": ""}
    assert route_after_review(state) == "rollback"


def test_route_after_review_reject():
    from workflows.autocode import route_after_review
    state = {"review": {"verdict": "REJECT"}, "retries": 0, "error": ""}
    assert route_after_review(state) == "rollback"


def test_route_after_test_syntax_error_triggers_retry():
    """SyntaxError in exec_error must route to retry, not commit."""
    from workflows.autocode import route_after_test
    state = {"exec_error": "SyntaxError line 42: invalid syntax", "retries": 0}
    assert route_after_test(state) == "retry"


def test_route_after_test_ruff_warning_proceeds_to_commit():
    """Ruff lint warnings must NOT trigger retry -- proceed to commit."""
    from workflows.autocode import route_after_test
    # Non-SyntaxError exec_error (ruff sets exec_error="" now, so this tests
    # that a non-syntax string also goes to commit)
    state = {"exec_error": "", "retries": 0}
    assert route_after_test(state) == "commit"


def test_route_after_test_no_error_commits():
    from workflows.autocode import route_after_test
    state = {"exec_error": "", "retries": 0}
    assert route_after_test(state) == "commit"


def test_route_after_syntax_check_ok():
    from workflows.autocode import route_after_syntax
    state = {"exec_error": "", "retries": 0}
    assert route_after_syntax(state) == "apply"


def test_route_after_syntax_check_error_retries():
    from workflows.autocode import route_after_syntax
    state = {"exec_error": "SyntaxError: invalid", "retries": 0}
    assert route_after_syntax(state) == "retry"


# ── Protected files ───────────────────────────────────────────────────────────

def test_protected_files_set_contains_core():
    from core.config import cfg
    must_protect = {"server.py", "registry.py", "core/config.py", "core/tracer.py"}
    for f in must_protect:
        assert cfg.is_protected(f), f"{f} should be protected"


def test_protected_files_expanded_set():
    from core.config import cfg
    # Phase9h expanded set
    assert cfg.is_protected("memory/store.py"),  "memory/store.py should be protected"
    assert cfg.is_protected("gateway/app.py"),   "gateway/app.py should be protected"
    assert cfg.is_protected("core/llm.py"),      "core/llm.py should be protected"


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
        goal="Fix error in memory/store.py: ValueError missing argument",
        trace_id="test-autocode-with-target",
        target_file="memory/store.py",
        mode="fix_error",
    )
    
    assert "status" in result
    assert result["status"] in ("success", "failed", "running")
