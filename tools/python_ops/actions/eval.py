"""tools/python_ops/actions/eval.py — Safe expression evaluation (NEW in v1.0).

Even more restrictive than run mode:
  - Code MUST parse as a single expression (ast.parse(code, mode='eval')).
    Statements (assignments, loops, ifs, defs, with) are rejected.
  - The expression is validated with _validate_eval_ast (which composes
    _validate_sandbox_ast) — same security boundary as run mode.
  - Executes via eval() with SAFE_BUILTINS only.
  - The expression's VALUE is the output (no print() required).

json_schema behavior:
  When provided, the expression's value is validated against the schema.
  On mismatch, returns fail("Output does not match schema: ..."). This is
  strict (not graceful) because the value is a structured object, not
  arbitrary stdout text.
"""
from __future__ import annotations

import ast
import json
from typing import Any, Dict

from core.contracts import ok, fail
from tools.python_ops._registry import register_action
from tools.python_ops.sandbox import SAFE_BUILTINS, _validate_eval_ast
from tools.python_ops.executors import _validate_against_schema


def _parse_json_schema(json_schema: str) -> Dict | None:
    """Parse json_schema param string. Returns None on empty/invalid."""
    if not json_schema or not json_schema.strip():
        return None
    try:
        return json.loads(json_schema)
    except (json.JSONDecodeError, ValueError):
        return None


def _stringify(value: Any) -> str:
    """Stringify an eval result for display.

    Tries JSON for dict/list/bool/None/numbers; falls back to repr/str.
    JSON is preferred because it's the most LLM-friendly format for
    structured data.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)) or value is None or isinstance(value, (int, float, bool)):
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            pass
    return repr(value)


@register_action(
    "python", "eval",
    help_text="""eval — Safe expression evaluation (no statements, sandbox-validated).
Required: code (must be a single expression)
Optional: trace_id, json_schema (strict — value must match schema)
Returns: {data: str(result), mode: "eval"}""",
    examples=[
        'python(action="eval", code="2 + 2")',
        'python(action="eval", code="[x**2 for x in range(5)]")',
        'python(action="eval", code="sum(x for x in range(10) if x % 2 == 0)")',
    ],
)
def _action_eval(
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
    **kwargs: Any,
) -> dict:
    """Safe expression evaluation. The expression value IS the output."""
    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id, mode="eval")

    # _validate_eval_ast: must be pure expression AND pass sandbox safety.
    is_safe, err = _validate_eval_ast(code)
    if not is_safe:
        return fail(err, trace_id=trace_id, mode="eval")

    # Compile and evaluate with SAFE_BUILTINS only.
    try:
        compiled = compile(ast.parse(code, mode='eval'), '<string>', 'eval')
        result_value = eval(compiled, {"__builtins__": SAFE_BUILTINS})
    except Exception as e:
        return fail(str(e), trace_id=trace_id, mode="eval")

    # json_schema validation (STRICT — fail on mismatch)
    schema_dict = _parse_json_schema(json_schema)
    if schema_dict is not None:
        ok_, err = _validate_against_schema(result_value, schema_dict)
        if not ok_:
            return fail(
                f"Output does not match schema: {err}",
                trace_id=trace_id,
                mode="eval",
            )
    elif json_schema and json_schema.strip():
        return fail(
            "json_schema was provided but is not valid JSON.",
            trace_id=trace_id,
            mode="eval",
        )

    final_output = _stringify(result_value)
    result = ok(final_output, mode="eval")
    if trace_id:
        result["trace_id"] = trace_id
    return result
