"""tests/workflows/understand/test_helpers.py

[v1.4.2 SPLIT] This file now contains ONLY the helper-module tests:
  - TestChunkedMd5    — tests _chunked_md5() in workflows.understand_impl.helpers
  - TestTraceIdPropagation — tests node source for hardcoded tids

The structural/regression tests (TestSyncNodes, TestNoEventLoopHack,
TestSubpackageStructure, TestCompletedWithErrors) were moved to
test_structure.py — they're not helper-module tests, they're graph-level
invariants.
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
                isinstance(node.body[0].value, ast.Constant) and
                isinstance(node.body[0].value.value, str)):
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
