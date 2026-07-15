"""tools/python_ops/actions/run_data.py — Controlled-imports action.

Preserves the original tools/python.py `mode="run_data"` behavior:
  1. Syntax check (ast.parse).
  2. Parse imports via _parse_imports.
  3. Reject BLOCKED_IMPORTS (security boundary).
  4. Reject imports not in ALL_ALLOWED.
  5. Route to _run_inprocess (stdlib only) or _run_subprocess (heavy libs).
  6. Prune large outputs via prune_text.

v1.0 changes vs legacy run_data mode:
  - Routed through @register_action("python", "run_data").
  - Accepts trace_id, timeout (forwards to _run_subprocess), json_schema.
  - When json_schema is provided, attempts to validate the output as JSON
    against the schema. On failure, appends a warning to the result but
    returns the original output as-is (graceful degradation).
"""
from __future__ import annotations

import ast
import json
from typing import Any, Dict

from core.contracts import ok, fail
from core.memory_backend.pruner import prune_text
from tools.python_ops._registry import register_action
from tools.python_ops.imports import (
    ALL_ALLOWED,
    BLOCKED_IMPORTS,
    HEAVY_IMPORTS,
    STDLIB_IMPORTS,
    _parse_imports,
)
from tools.python_ops.executors import (
    _run_inprocess,
    _run_subprocess,
    _validate_output_text_against_schema,
)


def _parse_json_schema(json_schema: str) -> Dict | None:
    """Parse json_schema param string. Returns None on empty/invalid."""
    if not json_schema or not json_schema.strip():
        return None
    try:
        return json.loads(json_schema)
    except (json.JSONDecodeError, ValueError):
        return None


@register_action(
    "python", "run_data",
    help_text="""run_data — Controlled imports (stdlib in-process, heavy in subprocess).
Required: code
Optional: trace_id, timeout (-1 = default), json_schema
Returns: {data: stdout output, mode: "in_process" | "subprocess"}""",
    examples=[
        'python(action="run_data", code="import json; print(json.dumps({\'a\': 1}))")',
        'python(action="run_data", code="import pandas as pd; print(pd.Series([1,2,3]).mean())")',
    ],
)
def _action_run_data(
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
    **kwargs: Any,
) -> dict:
    """Controlled-imports execution with stdlib/heavy routing."""
    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id, mode="run_data")

    # Syntax check first
    try:
        ast.parse(code)
    except SyntaxError as e:
        return fail(f"SyntaxError line {e.lineno}: {e.msg}", trace_id=trace_id, mode="run_data")

    imports = _parse_imports(code)

    # Check blocked imports first (security boundary)
    dangerous = [n for n in imports if n in BLOCKED_IMPORTS]
    if dangerous:
        return fail(
            f"Import(s) blocked for security: {dangerous}. "
            "These modules can access filesystem, processes, or network. "
            "Use the file(), git(), or web() tools instead.",
            trace_id=trace_id,
            mode="run_data",
        )

    blocked = [n for n in imports if n not in ALL_ALLOWED and n not in ("__future__",)]
    if blocked:
        return fail(
            f"Import(s) not in allowed list: {blocked}. "
            f"Allowed stdlib: {sorted(STDLIB_IMPORTS)}. "
            f"Allowed heavy: {sorted(HEAVY_IMPORTS)}.",
            trace_id=trace_id,
            mode="run_data",
        )

    needs_heavy = any(n in HEAVY_IMPORTS for n in imports)
    if needs_heavy:
        result = _run_subprocess(code, timeout_override=timeout)
    else:
        result = _run_inprocess(code, imports)

    # Prune large outputs (only on success)
    if result.get("status") == "success" and result.get("data"):
        result["data"] = prune_text("python_exec", result["data"], trace_id)

    # json_schema validation (graceful — append warning, return output as-is)
    schema_dict = _parse_json_schema(json_schema)
    warnings: list = []
    if schema_dict is not None and result.get("status") == "success" and result.get("data"):
        validated, warnings = _validate_output_text_against_schema(
            result["data"], schema_dict
        )
        result["data"] = validated
    elif json_schema and json_schema.strip():
        warnings.append(
            "json_schema was provided but is not valid JSON — schema check skipped."
        )

    if warnings:
        result["warnings"] = warnings
    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id
    return result
