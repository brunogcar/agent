"""tools/python_ops/actions/run.py — Sandbox action (strict, no imports).

Preserves the original tools/python.py `mode="run"` behavior:
  1. Fast-path string check (FORBIDDEN_IN_SANDBOX).
  2. Authoritative AST validation (_validate_sandbox_ast).
  3. Execute with SAFE_BUILTINS + _STDOUT_LOCK guarding stdout capture.
  4. If no print() output, fall back to stringified local vars.
  5. Prune large outputs via prune_text.
  6. Return ok(output, mode="sandbox") or fail(error, mode="sandbox").

v1.0 changes vs legacy run mode:
  - Routed through @register_action("python", "run").
  - Accepts trace_id, timeout (ignored — run is in-process), json_schema params.
  - When json_schema is provided, attempts to validate the output as JSON
    against the schema. On failure, appends a warning to the result but
    returns the original output as-is (graceful degradation).
"""
from __future__ import annotations

import contextlib
import io
import json
from typing import Any, Dict

from core.contracts import ok, fail
from core.memory_backend.pruner import prune_text
from tools.python_ops._registry import register_action
from tools.python_ops.sandbox import (
    FORBIDDEN_IN_SANDBOX,
    SAFE_BUILTINS,
    _validate_sandbox_ast,
)
from tools.python_ops.executors import (
    _STDOUT_LOCK,
    _validate_output_text_against_schema,
)


def _parse_json_schema(json_schema: str) -> Dict | None:
    """Parse json_schema param string. Returns None on empty/invalid."""
    if not json_schema or not json_schema.strip():
        return None
    try:
        return json.loads(json_schema)
    except (json.JSONDecodeError, ValueError):
        # Caller will see no schema enforcement; surface via warnings later.
        return None


@register_action(
    "python", "run",
    help_text="""run — Strict sandbox, no imports, whitelisted builtins only.
Required: code
Optional: trace_id, json_schema (timeout ignored — run is in-process)
Returns: {data: stdout output | str(locals), mode: "sandbox"}""",
    examples=[
        'python(action="run", code="print(2 + 2)")',
        'python(action="run", code="x = [1,2,3]; print(sum(x))")',
    ],
)
def _action_run(
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
    **kwargs: Any,
) -> dict:
    """Strict sandbox execution. No imports, no dangerous builtins, no I/O."""
    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id, mode="sandbox")

    # Fast-path string check (cheap, catches obvious violations)
    for token in FORBIDDEN_IN_SANDBOX:
        if token in code:
            return fail(
                f"Forbidden token '{token}' in sandbox mode. "
                "Use action='run_data' for code that needs imports or file access.",
                trace_id=trace_id,
                mode="sandbox",
            )

    # 🔴 Authoritative AST validation (blocks obfuscated bypasses)
    ast_safe, ast_err = _validate_sandbox_ast(code)
    if not ast_safe:
        return fail(ast_err, trace_id=trace_id, mode="sandbox")

    captured = io.StringIO()
    try:
        with _STDOUT_LOCK:
            with contextlib.redirect_stdout(captured):
                local_env: Dict = {}
                exec(code, {"__builtins__": SAFE_BUILTINS}, local_env)
        output = captured.getvalue().strip()

        # If no print() output, fall back to stringified local vars.
        final_output = output if output else str({k: str(v) for k, v in local_env.items()})
        if output:  # Only prune actual stdout, not env dumps
            final_output = prune_text("python_exec", final_output, trace_id)

        # json_schema validation (graceful — append warning, return output as-is)
        warnings: list = []
        schema_dict = _parse_json_schema(json_schema)
        if schema_dict is not None:
            final_output, warnings = _validate_output_text_against_schema(
                final_output, schema_dict
            )
        elif json_schema and json_schema.strip():
            warnings.append(
                "json_schema was provided but is not valid JSON — schema check skipped."
            )

        result = ok(final_output, mode="sandbox")
        if warnings:
            result["warnings"] = warnings
        if trace_id:
            result["trace_id"] = trace_id
        return result
    except Exception as e:
        return fail(str(e), trace_id=trace_id, mode="sandbox")
