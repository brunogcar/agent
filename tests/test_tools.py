"""
tests/test_tools.py -- Unit tests for meta-tools

Run from D:/mcp/agent/:
    pytest tests/test_tools.py -v

Tests:
  - Python sandbox allows safe builtins
  - Python sandbox blocks dangerous tokens and imports
  - File tool path safety
  - Router heuristic routing correctness
  - Workflow status propagation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Python sandbox (mode="run") ───────────────────────────────────────────────

def test_sandbox_basic_math():
    from tools.python_exec import python
    r = python(mode="run", code="print(2 + 2)")
    assert r["status"] == "success"
    assert r["output"] == "4"


def test_sandbox_list_comprehension():
    from tools.python_exec import python
    r = python(mode="run", code="print([i**2 for i in range(5)])")
    assert r["status"] == "success"
    assert "16" in r["output"]


def test_sandbox_blocks_import():
    from tools.python_exec import python
    r = python(mode="run", code="import os")
    assert r["status"] == "error"
    assert "__import__" in r["error"] or "Forbidden" in r["error"]


def test_sandbox_blocks_eval():
    from tools.python_exec import python
    r = python(mode="run", code="eval('1+1')")
    assert r["status"] == "error"


def test_sandbox_blocks_exec():
    from tools.python_exec import python
    r = python(mode="run", code="exec('x=1')")
    assert r["status"] == "error"


def test_sandbox_allows_safe_builtins():
    from tools.python_exec import python
    r = python(mode="run", code="print(len([1,2,3]))")
    assert r["status"] == "success"
    assert r["output"] == "3"


def test_sandbox_does_not_contain_hash():
    """hash() must not be in SAFE_BUILTINS (DoS risk)."""
    from tools.python_exec import SAFE_BUILTINS
    assert "hash" not in SAFE_BUILTINS, "hash must not be in SAFE_BUILTINS"


# ── Python run_data (imports) ─────────────────────────────────────────────────

def test_run_data_stdlib():
    from tools.python_exec import python
    r = python(mode="run_data", code="import json\nprint(json.dumps({'a': 1}))")
    assert r["status"] == "success"
    assert '"a"' in r["output"]


def test_run_data_blocks_os():
    from tools.python_exec import python
    r = python(mode="run_data", code="import os\nprint(os.getcwd())")
    assert r["status"] == "error"
    assert "blocked for security" in r["error"]


def test_run_data_blocks_subprocess():
    from tools.python_exec import python
    r = python(mode="run_data", code="import subprocess\nsubprocess.run(['echo', 'hi'])")
    assert r["status"] == "error"
    assert "blocked for security" in r["error"]


def test_run_data_blocks_sys():
    from tools.python_exec import python
    r = python(mode="run_data", code="import sys\nprint(sys.path)")
    assert r["status"] == "error"
    assert "blocked for security" in r["error"]


def test_run_data_syntax_error_caught():
    from tools.python_exec import python
    r = python(mode="run_data", code="def f(\n    pass")
    assert r["status"] == "error"
    assert "SyntaxError" in r["error"]


def test_blocked_imports_set_coverage():
    """BLOCKED_IMPORTS must cover the most dangerous modules."""
    from tools.python_exec import BLOCKED_IMPORTS
    must_block = {"os", "sys", "subprocess", "shutil", "socket", "pickle"}
    missing    = must_block - BLOCKED_IMPORTS
    assert not missing, f"Missing from BLOCKED_IMPORTS: {missing}"


# ── File tool path safety ─────────────────────────────────────────────────────

def test_file_path_traversal_blocked():
    """Path traversal outside allowed roots must be blocked."""
    from tools.file_ops import file
    r = file(action="read", path="../../etc/passwd")
    assert r["status"] == "error"
    assert "outside allowed" in r["error"]


def test_file_write_and_read_roundtrip():
    """Write then read a file in the workspace."""
    from tools.file_ops import file
    test_path = "autocode/unit_test_roundtrip.txt"
    content   = f"unit test content"
    w = file(action="write", path=test_path, content=content)
    assert w["status"] == "success"
    r = file(action="read", path=test_path)
    assert r["status"] == "success"
    assert content in r["content"]


def test_file_list_returns_entries():
    from tools.file_ops import file
    r = file(action="list", path=".")
    assert r["status"] == "success"
    assert r["count"] > 0
    names = [e["name"] for e in r["entries"]]
    assert "server.py" in names


def test_file_write_protected_blocked():
    """Writing to server.py must be blocked."""
    from tools.file_ops import file
    r = file(action="write", path="server.py", content="# tampered")
    assert r["status"] == "error"
    assert "protected" in r["error"].lower()


# ── Router heuristic ──────────────────────────────────────────────────────────

def test_router_heuristic_code_keywords():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("fix the bug in tools/web.py")
    assert d.workflow == "autocode"


def test_router_heuristic_data_keywords():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("analyse the sales csv with pandas")
    assert d.workflow == "data"


def test_router_heuristic_visualize_keywords():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("create a bar chart of monthly revenue")
    assert d.workflow == "direct"
    assert d.tool == "visualize"


def test_router_heuristic_file_direct():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("read the config file")
    assert d.workflow == "direct"
    assert d.tool == "file"


def test_router_heuristic_defaults_to_research():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("something completely unrelated")
    assert d.workflow == "research"


def test_routing_decision_has_required_fields():
    from routing.router import TaskRouter
    r = TaskRouter()
    d = r._heuristic_route("what is chromadb")
    assert hasattr(d, "workflow")
    assert hasattr(d, "tool")
    assert hasattr(d, "complexity")
    assert hasattr(d, "reason")
    assert hasattr(d, "confidence")
    assert 1 <= d.complexity <= 10
