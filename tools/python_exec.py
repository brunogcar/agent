"""
tools/python_exec.py — Python execution meta-tool.

Replaces: run_python + run_python_data (old flat tools)
The LLM sees ONE tool: python(mode, code)

Modes:
  run      → strict sandbox, whitelisted builtins only, no imports
             Use for: pure logic, string ops, math, list/dict work
  run_data → two-path execution:
               stdlib imports → in-process (fast)
               heavy libs     → subprocess (isolated)
             Use for: anything that needs import statements

Key improvements over old execution.py:
  - Cleaner error messages that tell the model exactly what went wrong
  - FORBIDDEN_TOKENS no longer blocks subprocess (was a bug in old git_ops)
  - Sandbox uses pathlib-safe temp directory
  - Always print() — clear reminder in docstring
"""

from __future__ import annotations

import ast
import importlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.config import cfg
from registry import tool

# ── Sandbox config ────────────────────────────────────────────────────────────

SAFE_BUILTINS = {
    "print": print, "range": range, "len": len,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "isinstance": isinstance, "issubclass": issubclass,
    "type": type, "repr": repr,  # hash removed: DoS risk via collision
    "any": any, "all": all,
    "chr": chr, "ord": ord, "hex": hex, "oct": oct, "bin": bin,
    "divmod": divmod, "pow": pow,
    "True": True, "False": False, "None": None,
}

FORBIDDEN_IN_SANDBOX = ["__import__", "eval(", "exec(", "open(", "compile("]

# 🔴 AST Sandbox Validation (Security P0)
# Replaces brittle string-matching with syntax-tree analysis.
# Blocks imports, dangerous builtins, and module attribute access.
DANGEROUS_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__",
    "input", "breakpoint", "globals", "locals", "vars", "dir"
}
DANGEROUS_MODULES = {"os", "sys", "subprocess", "shutil", "socket", "ctypes", "multiprocessing"}

def _validate_sandbox_ast(code: str) -> tuple[bool, str]:
    """
    AST-based sandbox validation. Blocks imports and dangerous builtin calls.
    Returns (is_safe, error_message).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} (line {e.lineno})"

    for node in ast.walk(tree):
        # Block all imports in strict sandbox
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Imports are not allowed in sandbox mode. Use mode='run_data' for imports."

        # Block dangerous function calls
        if isinstance(node, ast.Call):
            func = node.func
            # Direct calls: eval(), exec(), open(), etc.
            if isinstance(func, ast.Name) and func.id in DANGEROUS_BUILTINS:
                return False, f"Blocked dangerous call: {func.id}() in sandbox mode."
            # Attribute calls: os.system(), subprocess.run(), etc.
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id in DANGEROUS_MODULES:
                    return False, f"Blocked dangerous module access: {func.value.id}.{func.attr}() in sandbox mode."

    return True, ""

# Stdlib modules — run in-process (fast, no subprocess overhead)
STDLIB_IMPORTS = {
    "random", "json", "math", "statistics", "datetime", "calendar",
    "collections", "itertools", "functools", "re", "csv",
    "io", "textwrap", "string", "decimal", "fractions",
    "heapq", "bisect", "pprint", "copy", "time", "uuid",
    "pathlib", "os", "sys", "hashlib", "base64", "struct",
    "dataclasses", "typing", "enum", "abc",
}

# Heavy libs — require subprocess (slow first import, worth isolating)
HEAVY_IMPORTS = {
    "pandas", "numpy", "matplotlib", "scipy", "sklearn",
    "seaborn", "plotly", "PIL", "cv2", "torch", "tensorflow",
}

ALL_ALLOWED = STDLIB_IMPORTS | HEAVY_IMPORTS

# Modules that are never allowed even in run_data -- security boundary.
# These can access the filesystem, network, processes, or environment vars.
BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "socket", "pickle",
    "multiprocessing", "ctypes", "importlib", "builtins",
    "signal", "pty", "tty", "termios", "fcntl", "resource",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_imports(code: str) -> list[str]:
    """Return list of top-level base module names from code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module.split(".")[0])
    return names


def _run_inprocess(code: str, import_names: list[str]) -> dict:
    """Execute stdlib-only code in-process. Fast, no subprocess overhead."""
    exec_globals: dict = {"__builtins__": __builtins__}

    for name in import_names:
        try:
            exec_globals[name] = importlib.import_module(name)
        except ImportError as e:
            return {"status": "error", "error": f"Import failed: {e}"}

    old_stdout = sys.stdout
    sys.stdout  = captured = io.StringIO()

    try:
        exec(code, exec_globals)
        output = captured.getvalue().strip()
        return {
            "status": "success",
            "output": output if output else "(no output — use print() to return results)",
            "mode":   "in_process",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "mode": "in_process"}
    finally:
        sys.stdout = old_stdout


def _run_subprocess(code: str) -> dict:
    """Execute heavy-lib code in a subprocess."""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
            dir=str(cfg.workspace_root),
        ) as f:
            f.write(code)
            tmp = Path(f.name)

        result = subprocess.run(
            [sys.executable, str(tmp)],
            capture_output=True,
            text=True,
            timeout=cfg.execution_timeout,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return {"status": "error", "error": error, "mode": "subprocess"}

        output = result.stdout.strip()
        return {
            "status": "success",
            "output": output if output else "(no output — use print() to return results)",
            "mode":   "subprocess",
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error":  f"Timed out after {cfg.execution_timeout}s. Simplify or reduce data size.",
            "mode":   "subprocess",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "mode": "subprocess"}
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def python(mode: str, code: str) -> dict:
    """
    Execute Python code.

    mode: "run" | "run_data"

    run
        Strict sandbox — no imports allowed.
        Only whitelisted built-ins: print, range, len, int, float, str,
        list, dict, set, sum, min, max, abs, round, sorted, zip, etc.
        Use for: math, string ops, list/dict manipulation, pure logic.
        Fast — runs in the current process.

    run_data
        Unrestricted imports from allowed module list.
        Stdlib modules (json, math, datetime, re, csv, etc.) → in-process, fast.
        Heavy libs (pandas, numpy, matplotlib, sklearn) → subprocess, isolated.
        ALWAYS use print() to return output — variables are not captured.
        Use for: data analysis, file processing, calculations with libraries.

    Allowed imports for run_data:
        stdlib: random json math statistics datetime calendar collections
                itertools functools re csv io textwrap string decimal
                pathlib os sys hashlib base64 uuid dataclasses typing enum
        heavy:  pandas numpy matplotlib scipy sklearn seaborn plotly

    Examples:
        python(mode="run", code="x = [i**2 for i in range(10)]\\nprint(sum(x))")

        python(mode="run_data", code='''
    import pandas as pd
    import json
    df = pd.DataFrame({"a": [1,2,3], "b": [4,5,6]})
    print(df.describe().to_json())
    ''')
    """
    mode = mode.strip().lower()

    if not code or not code.strip():
        return {"status": "error", "error": "No code provided"}

    # ── run (sandbox) ─────────────────────────────────────────────────────────
    if mode == "run":
        # Fast-path string check (cheap, catches obvious violations)
        for token in FORBIDDEN_IN_SANDBOX:
            if token in code:
                return {
                    "status": "error",
                    "error": (
                        f"Forbidden token '{token}' in sandbox mode. "
                        "Use mode='run_data' for code that needs imports or file access."
                    ),
                }
    
        # 🔴 Authoritative AST validation (blocks obfuscated bypasses)
        ast_safe, ast_err = _validate_sandbox_ast(code)
        if not ast_safe:
            return {"status": "error", "error": ast_err}

        try:
            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()
            local_env: dict = {}
            exec(code, {"__builtins__": SAFE_BUILTINS}, local_env)
            output = captured.getvalue().strip()
            sys.stdout = old_stdout
            return {
                "status": "success",
                "output": output if output else str({k: str(v) for k, v in local_env.items()}),
                "mode":    "sandbox",
            }
        except Exception as e:
            sys.stdout = old_stdout
            return {"status": "error", "error": str(e), "mode": "sandbox"}

    # ── run_data ──────────────────────────────────────────────────────────────
    if mode == "run_data":
        # Syntax check first
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "error",
                "error":  f"SyntaxError line {e.lineno}: {e.msg}",
                "mode":   "run_data",
            }

        imports = _parse_imports(code)
        # Check blocked imports first (security boundary)
        dangerous = [n for n in imports if n in BLOCKED_IMPORTS]
        if dangerous:
            return {
                "status": "error",
                "error": (
                    f"Import(s) blocked for security: {dangerous}. "
                    "These modules can access filesystem, processes, or network. "
                    "Use the file(), git(), or web() tools instead."
                ),
                "mode": "run_data",
            }

        blocked = [n for n in imports if n not in ALL_ALLOWED and n not in ("__future__",)]
        if blocked:
            return {
                "status": "error",
                "error": (
                    f"Import(s) not in allowed list: {blocked}. "
                    f"Allowed stdlib: {sorted(STDLIB_IMPORTS)}. "
                    f"Allowed heavy: {sorted(HEAVY_IMPORTS)}."
                ),
                "mode": "run_data",
            }

        needs_heavy = any(n in HEAVY_IMPORTS for n in imports)
        if needs_heavy:
            return _run_subprocess(code)
        return _run_inprocess(code, imports)

    return {
        "status": "error",
        "error":  f"Unknown mode '{mode}'. Use: run | run_data",
    }
