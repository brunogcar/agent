"""tools/python_ops/sandbox.py — Sandbox configuration and AST validation.

Extracted from the original tools/python.py during v1.0 @meta_tool refactor.
Contains all sandbox-related constants and the two AST validators:
  - _validate_sandbox_ast(code): full statement-level validation (used by run)
  - _validate_eval_ast(code): expression-only validation (used by eval)

The constants below define the security boundary for sandbox mode:
  - SAFE_BUILTINS: whitelisted builtins exposed to sandboxed code.
  - FORBIDDEN_IN_SANDBOX: cheap string-matching fast path (catches obvious
    violations before AST parsing runs).
  - DANGEROUS_*: AST-level sets used by the validators to block escapes.

NOTE: This is defense-in-depth against LLM mistakes and prompt injection.
It is NOT a security boundary against determined adversarial code. Do not
expose to untrusted multi-tenant input without OS-level sandboxing.
"""
from __future__ import annotations

import ast
from typing import Tuple


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

# Fast-path string check (cheap, catches obvious violations before AST walk).
FORBIDDEN_IN_SANDBOX = ["__import__", "eval(", "exec(", "open(", "compile("]

# 🔴 AST Sandbox Validation (Security P0)
# Replaces brittle string-matching with syntax-tree analysis.
# Blocks imports, dangerous builtins, module attribute access, and
# MRO traversal vectors that bypass import-based restrictions.
DANGEROUS_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__",
    "input", "breakpoint", "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr"
}
DANGEROUS_MODULES = {"os", "sys", "subprocess", "shutil", "socket", "ctypes", "multiprocessing"}

# Attributes that enable MRO traversal and sandbox escapes.
# These allow finding arbitrary classes (e.g., subprocess.Popen) already
# loaded in the interpreter without needing __import__.
DANGEROUS_ATTRS = {
    "__class__", "__base__", "__bases__", "__subclasses__", "__mro__",
    "__dict__",
}

# Names that must not be accessed directly (bypass attribute checks).
# __builtins__ is a Name in the AST, not an Attribute.
DANGEROUS_NAMES = {"__builtins__"}


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_sandbox_ast(code: str) -> Tuple[bool, str]:
    """
    AST-based sandbox validation. Blocks imports, dangerous builtin calls,
    module attribute access, MRO traversal vectors, and dangerous name access.

    Returns (is_safe, error_message).

    NOTE: This is defense-in-depth against LLM mistakes and prompt injection.
    It is NOT a security boundary against determined adversarial code.
    Do not expose to untrusted multi-tenant input without OS-level sandboxing.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} (line {e.lineno})"

    for node in ast.walk(tree):
        # Block all imports in strict sandbox
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Imports are not allowed in sandbox mode. Use action='run_data' for imports."

        # Block dangerous name references (__builtins__)
        if isinstance(node, ast.Name) and node.id in DANGEROUS_NAMES:
            return False, f"Blocked sandbox escape vector: name '{node.id}' is not allowed in sandbox mode."

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

        # Block MRO traversal attribute access.
        # These bypass import restrictions by finding already-loaded classes
        # (e.g., subprocess.Popen) via the Python class hierarchy.
        if isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_ATTRS:
                return False, f"Blocked sandbox escape vector: attribute '{node.attr}' is not allowed in sandbox mode."

        # Block dynamic subscript resolution (e.g., __builtins__["eval"])
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                if node.slice.value in DANGEROUS_BUILTINS:
                    return False, f"Blocked dynamic subscript access to '{node.slice.value}' in sandbox mode."

        # Block definition-time execution vectors
        if isinstance(node, ast.ClassDef):
            return False, "Class definitions (metaclass attacks) are not allowed in sandbox mode."
        if isinstance(node, ast.AsyncFunctionDef):
            return False, "Async functions are not allowed in sandbox mode."
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return False, "Context managers (with statements) are not allowed in sandbox mode."

    return True, ""


def _validate_eval_ast(code: str) -> Tuple[bool, str]:
    """
    Validate that code is a pure expression AND passes sandbox safety checks.

    Stricter than _validate_sandbox_ast: rejects ALL statements (assignments,
    loops, ifs, function/class defs, with, etc.). Only ast.Expression / Expr
    (a single expression statement) is allowed.

    Returns (is_safe, error_message). is_safe is True only when:
      1. code parses as a single expression via ast.parse(code, mode='eval').
         If parsing in eval mode fails, the code contains statements.
      2. The expression passes _validate_sandbox_ast (no dangerous builtins,
         no MRO traversal, no imports, etc.).
    """
    # First, must parse as 'eval' mode (pure expression)
    try:
        ast.parse(code, mode='eval')
    except SyntaxError as e:
        return False, (
            f"eval mode only accepts expressions, not statements. "
            f"(line {e.lineno}: {e.msg})"
        )

    # Then apply standard sandbox validation.
    # Note: _validate_sandbox_ast re-parses in default 'exec' mode, which
    # accepts single expressions too (they become Module(body=[Expr(value=...)])).
    # The security walk is identical regardless of parse mode.
    return _validate_sandbox_ast(code)
