"""tools/python_ops/executors.py — Execution helpers for run_data and profile.

Extracted from the original tools/python.py during v1.0 @meta_tool refactor.
Contains the two execution paths plus the thread-safety lock:

  - _STDOUT_LOCK: threading.Lock guarding contextlib.redirect_stdout.
    contextlib.redirect_stdout is reentrant but NOT cross-thread-safe
    (sys.stdout is process-global). The lock serializes stdout redirection
    so concurrent python(action="run") calls don't clobber each other's
    captured output.

  - _run_inprocess(code, import_names): executes stdlib-only code in the
    current process. Imports the requested modules and exposes them as
    globals. Fast path.

  - _run_subprocess(code, timeout_override=-1): writes code to a temp .py
    file under cfg.workspace_root, runs `python <tmp>` in a subprocess,
    captures stdout/stderr, returns ok/fail. timeout_override=-1 means
    use cfg.execution_timeout; any non-negative value overrides it.

v1.0 changes:
  - _run_subprocess now accepts timeout_override param so the python()
    facade can pass `timeout` from the caller through to the subprocess.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

from core.config import cfg
from core.contracts import ok, fail


# [BUGFIX-2] Thread-safe stdout capture using contextlib.redirect_stdout.
# contextlib.redirect_stdout is reentrant but NOT cross-thread-safe:
# sys.stdout is process-global, so concurrent redirects from different
# threads can clobber each other. We add a module-level lock to prevent
# this — safe even if python_exec is added to PARALLEL_SAFE in the future.
_STDOUT_LOCK = threading.Lock()


def _run_inprocess(code: str, import_names: list) -> dict:
    """Execute stdlib-only code in-process. Fast, no subprocess overhead.

    Pre-loads each requested module into exec_globals so the code can use
    `import X`-equivalent access without going through exec's import machinery
    (which would bypass the allowlist if the code itself contained an import
    statement we missed).

    Captures stdout via contextlib.redirect_stdout. NOT thread-safe alone —
    callers in run mode hold _STDOUT_LOCK; this helper does NOT lock because
    run_data callers don't strictly need it (in-process imports are already
    serialized by the GIL for stdlib). The run action handler takes the lock
    explicitly.
    """
    exec_globals: Dict = {"__builtins__": __builtins__}

    for name in import_names:
        try:
            exec_globals[name] = importlib.import_module(name)
        except ImportError as e:
            return fail(f"Import failed: {e}")

    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            exec(code, exec_globals)
        output = captured.getvalue().strip()
        return ok(
            output if output else "(no output — use print() to return results)",
            mode="in_process",
        )
    except Exception as e:
        return fail(str(e), mode="in_process")


def _run_subprocess(code: str, timeout_override: int = -1) -> dict:
    """Execute heavy-lib code in a subprocess.

    Writes code to a temp .py file under cfg.workspace_root, runs it with
    the current Python interpreter, captures stdout/stderr, returns ok/fail.

    Args:
        code: Python source code to execute.
        timeout_override: -1 (default) → use cfg.execution_timeout.
                          Any non-negative int → override the timeout.

    The temp file is removed in a finally block; failures are tolerated.
    """
    timeout = cfg.execution_timeout if timeout_override < 0 else timeout_override
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
            timeout=timeout,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return fail(error, mode="subprocess")

        output = result.stdout.strip()
        return ok(
            output if output else "(no output — use print() to return results)",
            mode="subprocess",
        )

    except subprocess.TimeoutExpired:
        return fail(
            f"Timed out after {timeout}s. Simplify or reduce data size.",
            mode="subprocess",
        )
    except Exception as e:
        return fail(str(e), mode="subprocess")
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


# ── JSON schema validation helper ────────────────────────────────────────────
# Best-effort JSON schema validation without depending on the `jsonschema`
# package (not in requirements.txt). Handles the common subset of JSON Schema
# keywords: type, enum, required, properties, items. Sufficient for tool-output
# contract enforcement; not a full JSON Schema implementation.

_PY_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _validate_against_schema(value: Any, schema: Dict) -> Tuple[bool, str]:
    """Best-effort JSON schema validation.

    Supports a useful subset of JSON Schema: type, enum, required,
    properties (recursive), items (recursive).

    Returns (ok, error_message). ok=True means value matches schema.
    Empty/None schema is treated as a pass (no constraints).
    """
    if not schema:
        return True, ""

    expected_type = schema.get("type")
    if expected_type:
        # bool is a subclass of int in Python; treat boolean and integer
        # as mutually exclusive to avoid silent type confusion.
        if expected_type == "integer" and isinstance(value, bool):
            return False, f"expected integer, got boolean"
        if expected_type == "number" and isinstance(value, bool):
            return False, f"expected number, got boolean"
        py_type = _PY_TYPE_MAP.get(expected_type)
        if py_type is not None and not isinstance(value, py_type):
            return False, f"expected {expected_type}, got {type(value).__name__}"

    if "enum" in schema:
        if value not in schema["enum"]:
            return False, f"value not in allowed enum: {schema['enum']}"

    # Object: required + properties (recursive)
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                return False, f"missing required field: {k}"
        properties = schema.get("properties", {})
        for k, v in value.items():
            if k in properties:
                ok_, err = _validate_against_schema(v, properties[k])
                if not ok_:
                    return False, f"field '{k}': {err}"

    # Array: items (recursive)
    if isinstance(value, list) and "items" in schema:
        items_schema = schema["items"]
        for i, item in enumerate(value):
            ok_, err = _validate_against_schema(item, items_schema)
            if not ok_:
                return False, f"item[{i}]: {err}"

    return True, ""


def _validate_output_text_against_schema(
    output_text: str, schema_dict: Dict
) -> Tuple[str, list]:
    """Validate an output-text-as-JSON against a schema (graceful).

    Used by run and run_data: tries to parse output_text as JSON. If parsing
    fails OR validation fails, appends a warning to the output and returns it
    as-is. If validation passes, returns the original output unchanged.

    Returns (output_text, warnings_list).
    """
    warnings: list = []
    try:
        parsed = json.loads(output_text)
    except (json.JSONDecodeError, ValueError):
        warnings.append(
            "json_schema was provided but output is not valid JSON — schema check skipped."
        )
        return output_text, warnings

    ok_, err = _validate_against_schema(parsed, schema_dict)
    if not ok_:
        warnings.append(f"json_schema validation failed: {err}")
    return output_text, warnings

