"""tests/workflows/understand/test_helpers.py
Tests for helpers, sync node verification, trace ID propagation,
no event loop hacks, and subpackage structure verification.
"""
from __future__ import annotations

import inspect
import ast
import hashlib
from pathlib import Path

from workflows.understand_impl.helpers import _chunked_md5


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


class TestChunkedMd5:
    """[Bug #6] _chunked_md5 must work correctly."""

    def test_chunked_md5_matches_standard(self, tmp_path):
        """Chunked MD5 must produce same hash as read_bytes()."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world", encoding="utf-8")
        chunked = _chunked_md5(test_file)
        standard = hashlib.md5(test_file.read_bytes()).hexdigest()
        assert chunked == standard

    def test_chunked_md5_large_file(self, tmp_path):
        """Chunked MD5 must work on files larger than chunk_size."""
        test_file = tmp_path / "large.py"
        test_file.write_text("x" * 20000, encoding="utf-8")
        chunked = _chunked_md5(test_file, chunk_size=8192)
        standard = hashlib.md5(test_file.read_bytes()).hexdigest()
        assert chunked == standard

    def test_chunked_md5_empty_file(self, tmp_path):
        """Chunked MD5 must work on empty files."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("", encoding="utf-8")
        chunked = _chunked_md5(test_file)
        standard = hashlib.md5(test_file.read_bytes()).hexdigest()
        assert chunked == standard


class TestTraceIdPropagation:
    """[Bug #1] All nodes must use state.get('trace_id') instead of hardcoded strings."""

    def test_no_hardcoded_tid_in_init(self):
        """node_init_project must not use hardcoded 'understand_init' in actual code."""
        from workflows.understand_impl.nodes.init_project import node_init_project
        source = inspect.getsource(node_init_project)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_init" not in code_str, (
            "node_init_project must use state.get('trace_id'), not hardcoded 'understand_init'"
        )

    def test_no_hardcoded_tid_in_discover(self):
        """node_discover_files must not use hardcoded 'understand_discover' in actual code."""
        from workflows.understand_impl.nodes.discover_files import node_discover_files
        source = inspect.getsource(node_discover_files)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_discover" not in code_str, (
            "node_discover_files must use state.get('trace_id'), not hardcoded 'understand_discover'"
        )

    def test_no_hardcoded_tid_in_parse(self):
        """node_parse_and_store must not use hardcoded 'understand_parse' in actual code."""
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
        source = inspect.getsource(node_parse_and_store)
        code_str = _strip_comments_and_docstrings(source)
        assert "understand_parse" not in code_str, (
            "node_parse_and_store must use state.get('trace_id'), not hardcoded 'understand_parse'"
        )

    def test_no_hardcoded_tid_in_report(self):
        """node_report must not use hardcoded tid strings in actual code."""
        from workflows.understand_impl.nodes.report import node_report
        source = inspect.getsource(node_report)
        code_str = _strip_comments_and_docstrings(source)
        # node_report uses state.get("trace_id", "understand") as fallback — that's OK.
        # The bug was hardcoded "understand_init" etc. — "understand" as fallback is fine.
        assert "understand_init" not in code_str
        assert "understand_discover" not in code_str
        assert "understand_parse" not in code_str


class TestSyncNodes:
    """[Architecture] All nodes must be sync (def, not async def)."""

    def test_init_is_sync(self):
        from workflows.understand_impl.nodes.init_project import node_init_project
        assert not inspect.iscoroutinefunction(node_init_project), (
            "node_init_project must be sync (def, not async def)"
        )

    def test_discover_is_sync(self):
        from workflows.understand_impl.nodes.discover_files import node_discover_files
        assert not inspect.iscoroutinefunction(node_discover_files), (
            "node_discover_files must be sync (def, not async def)"
        )

    def test_parse_is_sync(self):
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
        assert not inspect.iscoroutinefunction(node_parse_and_store), (
            "node_parse_and_store must be sync (def, not async def)"
        )

    def test_report_is_sync(self):
        from workflows.understand_impl.nodes.report import node_report
        assert not inspect.iscoroutinefunction(node_report), (
            "node_report must be sync (def, not async def)"
        )


class TestNoEventLoopHack:
    """[Bug #12] The dangerous ThreadPoolExecutor + new_event_loop() must be removed.

    These tests check the thin facade (workflows/understand.py), not the
    understand_impl package — the __init__.py is empty, so inspect.getsource
    would fail on it. The facade is where run_understand_workflow_sync lives.
    """

    def test_no_threadpool_executor(self):
        """understand.py facade must not use ThreadPoolExecutor in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "ThreadPoolExecutor" not in code_str, (
            "ThreadPoolExecutor must be removed — sync nodes don't need it"
        )

    def test_no_new_event_loop(self):
        """understand.py facade must not create new event loops in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "new_event_loop" not in code_str, (
            "new_event_loop must be removed — sync nodes don't need it"
        )

    def test_no_asyncio_gather(self):
        """understand.py facade must not use asyncio.gather in actual code."""
        import workflows.understand as mod
        source = inspect.getsource(mod)
        code_str = _strip_comments_and_docstrings(source)
        assert "asyncio.gather" not in code_str, (
            "asyncio.gather must be removed — sync nodes parse files directly"
        )


class TestSubpackageStructure:
    """[v1.0 refactor] Verify the understand_impl subpackage has the correct structure."""

    def test_state_module_exists(self):
        from workflows.understand_impl import state
        assert hasattr(state, "UnderstandState")
        assert hasattr(state, "_default_state")

    def test_graph_module_exists(self):
        from workflows.understand_impl import graph
        assert hasattr(graph, "build_understand_graph")
        assert hasattr(graph, "WORKFLOW_METADATA")

    def test_helpers_module_exists(self):
        from workflows.understand_impl import helpers
        assert hasattr(helpers, "_chunked_md5")

    def test_nodes_module_exists(self):
        from workflows.understand_impl.nodes import init_project
        from workflows.understand_impl.nodes import discover_files
        from workflows.understand_impl.nodes import parse_and_store
        from workflows.understand_impl.nodes import report
        assert hasattr(init_project, "node_init_project")
        assert hasattr(discover_files, "node_discover_files")
        assert hasattr(parse_and_store, "node_parse_and_store")
        assert hasattr(report, "node_report")

    def test_facade_reexports(self):
        """Thin facade must re-export build_understand_graph and _default_state."""
        from workflows.understand import build_understand_graph
        from workflows.understand import _default_state
        from workflows.understand import WORKFLOW_METADATA
        from workflows.understand import run_understand_workflow_sync
        assert callable(build_understand_graph)
        assert callable(_default_state)
        assert isinstance(WORKFLOW_METADATA, dict)
        assert callable(run_understand_workflow_sync)

    def test_graphstore_close_called_in_init(self):
        """[Bug #3/#4] node_init_project must close GraphStore after verifying."""
        source = inspect.getsource(
            __import__("workflows.understand_impl.nodes.init_project", fromlist=["node_init_project"]).node_init_project
        )
        code_str = _strip_comments_and_docstrings(source)
        assert "store.close()" in code_str, (
            "node_init_project must call store.close() after verifying GraphStore"
        )

    def test_graphstore_close_called_in_discover(self):
        """[Bug #4] node_discover_files must close GraphStore in finally block."""
        source = inspect.getsource(
            __import__("workflows.understand_impl.nodes.discover_files", fromlist=["node_discover_files"]).node_discover_files
        )
        code_str = _strip_comments_and_docstrings(source)
        assert "store.close()" in code_str, (
            "node_discover_files must call store.close()"
        )

    def test_graphstore_close_called_in_parse(self):
        """[Bug #4] node_parse_and_store must close GraphStore."""
        source = inspect.getsource(
            __import__("workflows.understand_impl.nodes.parse_and_store", fromlist=["node_parse_and_store"]).node_parse_and_store
        )
        code_str = _strip_comments_and_docstrings(source)
        assert "store.close()" in code_str, (
            "node_parse_and_store must call store.close()"
        )

    def test_dedup_target_paths_in_parse(self):
        """[Bug #7] node_parse_and_store must deduplicate target paths via set()."""
        source = inspect.getsource(
            __import__("workflows.understand_impl.nodes.parse_and_store", fromlist=["node_parse_and_store"]).node_parse_and_store
        )
        code_str = _strip_comments_and_docstrings(source)
        assert "set()" in code_str or "set(" in code_str, (
            "node_parse_and_store must use set() for deduplication"
        )

    def test_report_logs_errors(self):
        """[Bug #11] node_report must log exceptions via tracer.error, not silent pass."""
        source = inspect.getsource(
            __import__("workflows.understand_impl.nodes.report", fromlist=["node_report"]).node_report
        )
        code_str = _strip_comments_and_docstrings(source)
        assert "tracer.error" in code_str, (
            "node_report must use tracer.error() for exceptions (was silent except: pass)"
        )
        assert "pass" not in code_str.replace("pass_", "").replace("compass", ""), (
            "node_report must not have bare 'pass' in exception handler"
        )


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
