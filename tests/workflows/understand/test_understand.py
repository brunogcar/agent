"""
tests/workflows/understand/test_understand.py
Validates the Understand workflow structure and node logic.

[Architecture] All tests converted from async to sync — nodes are now sync (def, not async def).
"""
import ast
import inspect
import pytest
from pathlib import Path
from workflows.understand import (
    build_understand_graph,
    _default_state,
    node_init_project,
    _chunked_md5,
)


def _strip_comments_and_docstrings(source: str) -> str:
    """Strip docstrings and comments from source code for pattern matching."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
    code_only = ast.unparse(tree)
    code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
    return "\n".join(code_lines)


def test_build_understand_graph_compiles():
    """Ensure the LangGraph state machine compiles without errors."""
    graph = build_understand_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")


def test_default_state_structure(tmp_path):
    """Ensure _default_state creates the correct initial structure."""
    project_path = tmp_path / "test_proj"
    project_path.mkdir()
    (project_path / "code").mkdir()  # Workspace projects need source root

    state = _default_state(str(project_path), is_agent_root=False)

    assert state["project_path"] == str(project_path.resolve())
    assert state["status"] == "running"
    assert state["files_to_parse"] == []
    assert state["files_parsed"] == 0
    # [Bug #2] trace_id must be in default state
    assert "trace_id" in state


def test_default_state_includes_trace_id(tmp_path):
    """[Bug #2] _default_state must accept and inject trace_id."""
    project_path = tmp_path / "test_proj"
    project_path.mkdir()
    (project_path / "code").mkdir()

    state = _default_state(str(project_path), is_agent_root=False, trace_id="test-trace-123")
    assert state["trace_id"] == "test-trace-123"


def test_node_init_project_creates_dirs(tmp_path):
    """[Architecture] Sync version — was async. Ensure node_init_project creates dirs."""
    project_path = tmp_path / "test_proj"
    project_path.mkdir()
    (project_path / "code").mkdir()

    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    result = node_init_project(state)

    assert result["status"] == "running"
    assert (project_path / ".understand").exists()
    assert (project_path / ".understand" / "kg.db").exists()


def test_node_init_project_fails_without_code_dir(tmp_path):
    """Workspace projects without code/ directory must fail with clear error."""
    project_path = tmp_path / "bad_proj"
    project_path.mkdir()
    # Intentionally do NOT create code/ directory

    state = _default_state(str(project_path), is_agent_root=False, trace_id="test")
    result = node_init_project(state)

    assert result.get("status") == "failed", (
        "node_init_project must fail when source_root (code/) is missing"
    )
    assert "error" in result or "errors" in result, (
        "Error message must be present"
    )


class TestTraceIdPropagation:
    """[Bug #1] All nodes must use state.get('trace_id') instead of hardcoded strings."""

    def test_no_hardcoded_tid_in_init(self):
        """node_init_project must not use hardcoded 'understand_init' in actual code."""
        from workflows.understand import node_init_project
        source = inspect.getsource(node_init_project)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_init" not in code_str, (
            "node_init_project must use state.get('trace_id'), not hardcoded 'understand_init'"
        )

    def test_no_hardcoded_tid_in_discover(self):
        """node_discover_files must not use hardcoded 'understand_discover' in actual code."""
        from workflows.understand import node_discover_files
        source = inspect.getsource(node_discover_files)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_discover" not in code_str, (
            "node_discover_files must use state.get('trace_id'), not hardcoded 'understand_discover'"
        )

    def test_no_hardcoded_tid_in_parse(self):
        """node_parse_and_store must not use hardcoded 'understand_parse' in actual code."""
        from workflows.understand import node_parse_and_store
        source = inspect.getsource(node_parse_and_store)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_parse" not in code_str, (
            "node_parse_and_store must use state.get('trace_id'), not hardcoded 'understand_parse'"
        )


class TestSyncNodes:
    """[Architecture] All nodes must be sync (def, not async def)."""

    def test_init_is_sync(self):
        from workflows.understand import node_init_project
        assert not inspect.iscoroutinefunction(node_init_project), (
            "node_init_project must be sync (def, not async def)"
        )

    def test_discover_is_sync(self):
        from workflows.understand import node_discover_files
        assert not inspect.iscoroutinefunction(node_discover_files), (
            "node_discover_files must be sync (def, not async def)"
        )

    def test_parse_is_sync(self):
        from workflows.understand import node_parse_and_store
        assert not inspect.iscoroutinefunction(node_parse_and_store), (
            "node_parse_and_store must be sync (def, not async def)"
        )

    def test_report_is_sync(self):
        from workflows.understand import node_report
        assert not inspect.iscoroutinefunction(node_report), (
            "node_report must be sync (def, not async def)"
        )


class TestNoEventLoopHack:
    """[Bug #12] The dangerous ThreadPoolExecutor + new_event_loop() must be removed."""

    def test_no_threadpool_executor(self):
        """understand.py must not use ThreadPoolExecutor in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "ThreadPoolExecutor" not in code_str, (
            "ThreadPoolExecutor must be removed — sync nodes don't need it"
        )

    def test_no_new_event_loop(self):
        """understand.py must not create new event loops in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "new_event_loop" not in code_str, (
            "new_event_loop must be removed — sync nodes don't need it"
        )

    def test_no_asyncio_gather(self):
        """understand.py must not use asyncio.gather in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "asyncio.gather" not in code_str, (
            "asyncio.gather must be removed — sync nodes parse files directly"
        )


class TestChunkedMd5:
    """[Bug #6] _chunked_md5 must work correctly."""

    def test_chunked_md5_matches_standard(self, tmp_path):
        """Chunked MD5 must produce same hash as read_bytes()."""
        import hashlib
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world", encoding="utf-8")

        chunked = _chunked_md5(test_file)
        standard = hashlib.md5(test_file.read_bytes()).hexdigest()
        assert chunked == standard, "Chunked MD5 must match standard MD5"


class TestCompletedWithErrors:
    """[Bug #9] completed_with_errors must be treated as success."""

    def test_run_understand_workflow_sync_accepts_completed_with_errors(self):
        """run_understand_workflow_sync must treat 'completed_with_errors' as success."""
        from workflows.understand import run_understand_workflow_sync
        source = inspect.getsource(run_understand_workflow_sync)
        code_str = _strip_comments_and_docstrings(source)
        assert "completed_with_errors" in code_str, (
            "run_understand_workflow_sync must check for 'completed_with_errors' status"
        )
