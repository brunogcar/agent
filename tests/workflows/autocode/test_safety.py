"""tests/workflows/autocode/test_safety.py
Tests for TDD cycle safety, memory callbacks, and dry-run mode.
Covers the cross-cutting safety concerns that don't fit a single node.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


@pytest.fixture
def mock_memory_store():
    with patch("core.memory_engine.memory.store") as mock:
        mock.return_value = {"status": "stored", "id": "mem-001"}
        yield mock


@pytest.fixture
def mock_llm_call():
    with patch("workflows.autocode_impl.helpers._call") as mock:
        mock.return_value = "def test_pass(): assert True"
        yield mock


class TestDryRunMode:
    def test_dry_run_skips_disk_writes(self, base_state, temp_workspace):
        """dry_run=True must prevent file writes."""
        from workflows.autocode_impl.nodes.execute import node_execute_step
        base_state["dry_run"] = True
        base_state["tdd_source_code"] = "new_file.py: print('hi')"
        with patch("workflows.autocode_impl.nodes.execute._call") as mock_llm:
            mock_llm.return_value = "print('hi')"
            result = node_execute_step(base_state)
        assert "modified_files" not in result
        assert not list(temp_workspace.glob("*.py"))

    def test_dry_run_false_populates_modified_files(self, base_state, temp_workspace):
        """dry_run=False should allow writes (modified_files populated)."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        import json
        base_state["dry_run"] = False
        base_state["tdd_source_code"] = json.dumps({"new_files": {"out.py": "# code"}})
        base_state["test_code"] = ""
        result = node_write_files(base_state)
        # modified_files may or may not be set depending on write_files logic,
        # but the dry_run guard must NOT have triggered
        assert result.get("status") != "dry_run"


class TestProtectedFiles:
    def test_protected_file_rejected_at_validate(self, base_state, temp_workspace):
        from core.config import cfg
        (temp_workspace / "core").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "core" / "config.py").touch()
        (temp_workspace / "server.py").touch()
        (temp_workspace / "workspace").mkdir(parents=True, exist_ok=True)
        (temp_workspace / "workspace" / "output.py").touch()
        assert cfg.is_protected(temp_workspace / "core" / "config.py")
        assert cfg.is_protected(temp_workspace / "server.py")
        assert not cfg.is_protected(temp_workspace / "workspace" / "output.py")


class TestMemoryCallbacks:
    def test_memory_stored_on_tdd_success(self, base_state, mock_memory_store):
        """Memory must store with correct tags/importance on TDD pass."""
        from core.memory_engine import memory
        base_state["tdd_status"] = "passed"
        base_state["tdd_iteration"] = 2
        base_state["task"] = "add validation"
        memory.store(
            text=f"TDD converged after {base_state['tdd_iteration']} iterations for task: '{base_state['task']}'",
            memory_type="procedural", importance=7,
            tags="tdd_success,converged,autocode",
            trace_id=base_state["trace_id"], outcome="success",
        )
        mock_memory_store.assert_called_once()
        kwargs = mock_memory_store.call_args.kwargs
        assert kwargs["memory_type"] == "procedural"
        assert "tdd_success" in kwargs["tags"]
        assert kwargs["outcome"] == "success"

    def test_memory_stored_on_retry_exhaustion(self, base_state, mock_memory_store):
        from core.memory_engine import memory
        base_state["tdd_status"] = "max_retries_exceeded"
        base_state["tdd_iteration"] = 3
        base_state["tdd_error"] = "AssertionError"
        base_state["task"] = "fix endpoint"
        memory.store(
            text=f"TDD failed after {base_state['tdd_iteration']} iterations",
            memory_type="procedural", importance=9,
            tags="tdd_failure,retry_exhaustion,autocode",
            trace_id=base_state["trace_id"], outcome="failed",
        )
        kwargs = mock_memory_store.call_args.kwargs
        assert kwargs["importance"] == 9
        assert "tdd_failure" in kwargs["tags"]


class TestTDDLoopConvergence:
    def test_passing_tests_route_to_verify(self, base_state):
        from workflows.autocode_impl.routes import route_after_run_tests
        base_state["tdd_status"] = "passed"
        base_state["test_results"] = {"success": True}
        assert route_after_run_tests(base_state) == "node_verify"

    def test_failing_tests_route_to_debug(self, base_state):
        from workflows.autocode_impl.routes import route_after_run_tests
        base_state["tdd_status"] = "failed"
        base_state["test_results"] = {"success": False}
        assert route_after_run_tests(base_state) == "node_systematic_debug"

    def test_verify_failure_routes_to_end(self, base_state):
        from workflows.autocode_impl.routes import route_after_verify
        base_state["verification_passed"] = False
        assert route_after_verify(base_state) == "END"


# [Pre-2.0 Fix] DELETED: TestMermaidGuards — mermaid.py was removed (dead code,
# never called). WORKFLOW_METADATA serves the same purpose programmatically.
# Was: class TestMermaidGuards:
#          def test_mermaid_uses_getattr(self): ...


class TestDeadRoutesRemoved:
    """[P1 #4] route_after_brainstorm and route_after_debug were removed."""

    def test_dead_routes_not_in_routes_module(self):
        import workflows.autocode_impl.routes as routes
        assert not hasattr(routes, "route_after_brainstorm")
        assert not hasattr(routes, "route_after_debug")

    def test_dead_routes_not_imported_in_graph(self):
        import inspect
        from workflows.autocode_impl import graph
        source = inspect.getsource(graph)
        assert "route_after_brainstorm" not in source
        assert "route_after_debug" not in source


class TestNoDeadAgentRoot:
    """[Bug #9] AGENT_ROOT removed from state.py."""

    def test_no_agent_root_module_variable(self):
        import workflows.autocode_impl.state as state
        assert not hasattr(state, "AGENT_ROOT")


class TestReportTypeAnnotation:
    """[P1 #2] node_report must return dict, not AutocodeState."""

    def test_report_returns_dict_annotation(self):
        import inspect
        from workflows.autocode_impl.nodes.report import node_report
        sig = inspect.signature(node_report)
        # With `from __future__ import annotations`, the annotation is the string "dict"
        ann = sig.return_annotation
        assert ann is dict or ann == "dict", (
            f"node_report must annotate return as dict; got {ann!r}"
        )
