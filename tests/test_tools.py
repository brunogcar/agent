"""
tests/test_tools.py -- Unit tests for meta-tools
Run from D:/mcp/agent/: pytest tests/test_tools.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# -- Python sandbox (mode="run") ----------------------------------------------

def test_sandbox_basic_math():
    from tools.python_exec import python
    r = python(mode="run", code="print(2 + 2)")
    assert r["status"] == "success" and r["output"] == "4"

def test_sandbox_list_comprehension():
    from tools.python_exec import python
    r = python(mode="run", code="print([i**2 for i in range(5)])")
    assert r["status"] == "success" and "16" in r["output"]

def test_sandbox_blocks_import():
    from tools.python_exec import python
    r = python(mode="run", code="import os")
    assert r["status"] == "error"

def test_sandbox_blocks_eval():
    from tools.python_exec import python
    assert python(mode="run", code="eval('1+1')")["status"] == "error"

def test_sandbox_blocks_exec():
    from tools.python_exec import python
    assert python(mode="run", code="exec('x=1')")["status"] == "error"

def test_sandbox_allows_safe_builtins():
    from tools.python_exec import python
    r = python(mode="run", code="print(len([1,2,3]))")
    assert r["status"] == "success" and r["output"] == "3"

def test_sandbox_no_hash_builtin():
    from tools.python_exec import SAFE_BUILTINS
    assert "hash" not in SAFE_BUILTINS

# -- Python run_data ----------------------------------------------------------

def test_run_data_stdlib():
    from tools.python_exec import python
    r = python(mode="run_data", code='import json\nprint(json.dumps({"a": 1}))')
    assert r["status"] == "success" and '"a"' in r["output"]

def test_run_data_blocks_os():
    from tools.python_exec import python
    r = python(mode="run_data", code="import os\nprint(os.getcwd())")
    assert r["status"] == "error" and "blocked for security" in r["error"]

def test_run_data_blocks_subprocess():
    from tools.python_exec import python
    r = python(mode="run_data", code="import subprocess")
    assert r["status"] == "error" and "blocked for security" in r["error"]

def test_run_data_blocks_sys():
    from tools.python_exec import python
    r = python(mode="run_data", code="import sys\nprint(sys.path)")
    assert r["status"] == "error" and "blocked for security" in r["error"]

def test_run_data_syntax_error_caught():
    from tools.python_exec import python
    r = python(mode="run_data", code="def f(\n    pass")
    assert r["status"] == "error" and "SyntaxError" in r["error"]

def test_blocked_imports_coverage():
    from tools.python_exec import BLOCKED_IMPORTS
    must_block = {"os", "sys", "subprocess", "shutil", "socket", "pickle"}
    assert not (must_block - BLOCKED_IMPORTS), \
        f"Missing from BLOCKED_IMPORTS: {must_block - BLOCKED_IMPORTS}"

# -- File tool ----------------------------------------------------------------

def test_file_path_traversal_blocked():
    from tools.file_ops import file
    r = file(action="read", path="../../etc/passwd")
    assert r["status"] == "error" and "outside allowed" in r["error"]

def test_file_write_read_roundtrip():
    from tools.file_ops import file
    w = file(action="write", path="autocode/unit_test_roundtrip.txt",
             content="unit test content")
    assert w["status"] == "success"
    r = file(action="read", path="autocode/unit_test_roundtrip.txt")
    assert r["status"] == "success" and "unit test content" in r["content"]

def test_file_list_workspace_root():
    """list path='autocode' -- a directory we know exists."""
    from tools.file_ops import file
    r = file(action="list", path="autocode")
    assert r["status"] == "success"
    assert r["count"] >= 0  # may be empty but should not error

def test_file_list_agent_root():
    """list an absolute agent path to confirm server.py exists there."""
    from tools.file_ops import file
    from core.config import cfg
    r = file(action="list", path=str(cfg.agent_root))
    assert r["status"] == "success"
    names = [e["name"] for e in r["entries"]]
    assert "server.py" in names

def test_file_write_protected_blocked():
    from tools.file_ops import file
    r = file(action="write", path="server.py", content="# tampered")
    assert r["status"] == "error" and "protected" in r["error"].lower()

# -- Router heuristic ---------------------------------------------------------

def test_router_code_keywords():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("fix the bug in tools/web.py")
    assert d.workflow == "autocode"

def test_router_data_keywords():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("analyse the sales csv with pandas")
    assert d.workflow == "data"

def test_router_report_keywords():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("create a bar chart of monthly revenue")
    assert d.workflow == "direct" and d.tool == "report"

def test_router_file_direct():
    """Use exact phrase from _DIRECT_FILE keyword list."""
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("read file config.py")
    assert d.workflow == "direct" and d.tool == "file"

def test_router_git_direct():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("git status")
    assert d.workflow == "direct" and d.tool == "git"

def test_router_defaults_to_research():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("something completely unrelated xyz")
    assert d.workflow == "research"

def test_routing_decision_fields():
    from core.router import TaskRouter
    d = TaskRouter()._heuristic_route("what is chromadb")
    assert 1 <= d.complexity <= 10
    assert d.confidence in ("high", "medium", "low")
    assert isinstance(d.reason, str) and len(d.reason) > 0

