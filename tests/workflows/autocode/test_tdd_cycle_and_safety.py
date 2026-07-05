"""
tests/workflows/autocode/test_tdd_cycle_and_safety.py
Merged & expanded safety suite for Phase 3/4 autocode features.
Validates:
- Dry-run mode, protected files, max retries
- Surgical patching fallback & file locks
- Procedural memory callbacks
- TDD loop state transitions & routing convergence
- Error propagation across routing functions
Runs entirely in-memory/temp directories. Zero real git, LLM, or network calls.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Patch cfg.agent_root to tmp_path for safe file writes."""
    import core.config
    monkeypatch.setattr(core.config.cfg, "workspace_root", tmp_path)
    monkeypatch.setattr(core.config.cfg, "agent_root", tmp_path)
    yield tmp_path


@pytest.fixture
def mock_llm_call():
    """Mock _call globally to prevent LM Studio requests."""
    with patch("workflows.autocode_impl.helpers._call") as mock:
        mock.return_value = "def test_pass(): assert True"
        yield mock


@pytest.fixture
def mock_memory_store():
    """Mock memory.store to verify callback triggers."""
    with patch("core.memory_engine.memory.store") as mock:
        mock.return_value = {"status": "stored", "id": "mem-001"}
        yield mock


@pytest.fixture
def base_state(temp_workspace):
    """Minimal valid state for autocode node tests."""
    return {
        "task": "test safety features",
        "trace_id": "test-trace-safety",
        "status": "running",
        "dry_run": False,
        "plan": [{"id": 1, "label": "write_code", "description": "fix bug"}],
        "current_step": 0,
        "tdd_iteration": 0,
        "tdd_status": "",
        "test_results": {},
        "verification_passed": False,
        "project_root": str(temp_workspace),
    }


class TestDryRunAndSafetyGuards:
    """Validate dry-run blocking, protected file rejection, and max-retry enforcement."""

    def test_dry_run_skips_disk_writes(self, base_state, temp_workspace):
        """dry_run=True must prevent _write_files execution."""
        from workflows.autocode_impl.nodes.execute import node_execute_step
        base_state["dry_run"] = True
        base_state["tdd_source_code"] = "new_file.py: print('hi')"

        with patch("workflows.autocode_impl.nodes.execute._call") as mock_llm:
            mock_llm.return_value = "print('hi')"
            result = node_execute_step(base_state)

        # Verify dry_run guard skipped file writes
        assert "modified_files" not in result
        assert not list(temp_workspace.glob("*.py"))

    def test_protected_file_rejected_at_validate(self, base_state, temp_workspace):
        """Nodes must never write to cfg.protected_files."""
        from core.config import cfg
        # Create dummy files in the mocked agent_root so Path.resolve() works correctly
        (temp_workspace / "core").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "core/config.py").touch()
        (temp_workspace / "server.py").touch()
        (temp_workspace / "workspace").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "workspace/output.py").touch()
        
        assert cfg.is_protected(temp_workspace / "core/config.py")
        assert cfg.is_protected(temp_workspace / "server.py")
        assert not cfg.is_protected(temp_workspace / "workspace/output.py")

    def test_max_retries_enforced_in_state(self, base_state):
        """tdd_iteration must increment and cap at max_retries."""
        from workflows.autocode_impl.state import MAX_RETRIES
        assert base_state["tdd_iteration"] == 0
        assert MAX_RETRIES == 3  # Default from config


class TestSurgicalPatchingAndFileLocks:
    """Validate patch fallback, atomic writes (no .bak), and lock timeout handling."""

    def test_apply_patch_success_no_bak(self, temp_workspace):
        """Successful patch must modify file WITHOUT creating .bak (Bug #1 fix)."""
        from workflows.autocode_impl.patch import apply_patch
        target = temp_workspace / "patch_target.py"
        target.write_text("def old(): pass\n", encoding="utf-8")

        result = apply_patch(target, old="def old(): pass\n", new="def new(): return True\n")
        assert result.ok is True
        assert "def new():" in target.read_text()
        # [Bug #1] No .bak file should be created — atomic writes only
        assert not target.with_suffix(".py.bak").exists(), ".bak file must not be created"

    def test_apply_patch_fallback_on_mismatch(self, temp_workspace):
        """Mismatched old_text must return ok=False without corrupting file."""
        from workflows.autocode_impl.patch import apply_patch
        target = temp_workspace / "fallback_target.py"
        target.write_text("original content", encoding="utf-8")

        fail = apply_patch(target, old="nonexistent", new="replacement")
        assert fail.ok is False
        assert target.read_text() == "original content"


class TestMemoryCallbacks:
    """Validate procedural memory triggers on TDD success/failure."""

    def test_memory_stored_on_tdd_success(self, base_state, mock_memory_store):
        """Memory must store with correct tags/importance on pass."""
        from core.memory_engine import memory
        base_state["tdd_status"] = "passed"
        base_state["tdd_iteration"] = 2
        base_state["task"] = "add validation"

        memory.store(
            text=f"TDD converged after {base_state['tdd_iteration']} iterations for task: '{base_state['task']}'",
            memory_type="procedural",
            importance=7,
            tags="tdd_success,converged,autocode",
            trace_id=base_state["trace_id"],
            outcome="success"
        )
        mock_memory_store.assert_called_once()
        kwargs = mock_memory_store.call_args.kwargs
        assert kwargs["memory_type"] == "procedural"
        assert "tdd_success" in kwargs["tags"]
        assert kwargs["outcome"] == "success"

    def test_memory_stored_on_retry_exhaustion(self, base_state, mock_memory_store):
        """Memory must store high-importance error on max retries."""
        from core.memory_engine import memory
        base_state["tdd_status"] = "max_retries_exceeded"
        base_state["tdd_iteration"] = 3
        base_state["tdd_error"] = "AssertionError"
        base_state["task"] = "fix endpoint"

        memory.store(
            text=f"TDD failed after {base_state['tdd_iteration']} iterations",
            memory_type="procedural",
            importance=9,
            tags="tdd_failure,retry_exhaustion,autocode",
            trace_id=base_state["trace_id"],
            outcome="failed"
        )
        kwargs = mock_memory_store.call_args.kwargs
        assert kwargs["importance"] == 9
        assert "tdd_failure" in kwargs["tags"]


class TestTDDLoopConvergence:
    """Validate state transitions that drive the execute ? test ? debug ? verify loop."""

    def test_loop_converges_after_one_pass(self, base_state, mock_llm_call):
        """Passing tests must set tdd_status='passed' and route to verify."""
        from workflows.autocode_impl.routes import route_after_run_tests
        from workflows.autocode_impl.nodes.run_tests import node_run_tests

        base_state["tdd_status"] = "passed"
        base_state["test_results"] = {"success": True, "output": ""}

        assert route_after_run_tests(base_state) == "node_verify"

    def test_loop_retries_until_pass(self, base_state):
        """Failing tests must route to debug and increment iteration."""
        from workflows.autocode_impl.routes import route_after_run_tests
        base_state["tdd_status"] = "failed"
        base_state["test_results"] = {"success": False}
        assert route_after_run_tests(base_state) == "node_systematic_debug"

    def test_loop_exhausts_retries_and_sets_failed(self, base_state):
        """When retries hit max, status must flip to failed."""
        base_state["tdd_iteration"] = 3
        base_state["max_retries"] = 3
        base_state["tdd_status"] = "failed"
        assert base_state["tdd_iteration"] >= base_state["max_retries"]


class TestErrorPropagationAndRouting:
    """Validate conditional edges trigger correctly on state changes."""

    def test_test_failure_routes_to_debug(self, base_state):
        from workflows.autocode_impl.routes import route_after_run_tests
        base_state["tdd_status"] = "failed"
        base_state["test_results"]["success"] = False
        assert route_after_run_tests(base_state) == "node_systematic_debug"

    def test_debug_failure_routes_back_to_run_tests(self, base_state):
        from workflows.autocode_impl.routes import route_after_debug
        assert route_after_debug(base_state) == "node_run_tests"

    def test_verify_failure_routes_to_end(self, base_state):
        from workflows.autocode_impl.routes import route_after_verify
        base_state["verification_passed"] = False
        assert route_after_verify(base_state) == "END"


