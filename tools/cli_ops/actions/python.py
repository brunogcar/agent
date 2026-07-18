"""Python execution proxy for cli meta-tool.

Lazy imports python tool.
All functions auto-register via @register_action decorator.

[v1.2] CLI action names now map to the python tool's `action` parameter
(the python tool was previously called with a non-existent `mode` param,
which would have raised TypeError at runtime). Mapping:
  - "run"  → action="run"       (execute code)
  - "calc" → action="eval"      (evaluate expression, return result)
  - "data" → action="run_data"  (data analysis with pandas/matplotlib output)

Future AIs: if a new CLI action is added, extend `action_map` below —
do NOT fall back to passing `mode=` to the python tool (it doesn't have one).
"""
from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "python", "run",
    help_text="Execute Python code (shortcut: 'run `' or 'exec ').",
    examples=["run print('hello')", "exec 2+2"],
)
@register_action(
    "python", "calc",
    help_text="Calculate expression (shortcut: 'calc ').",
    examples=["calc 2+2", "calc len([1,2,3])"],
)
@register_action(
    "python", "data",
    help_text="Run data analysis code.",
    examples=["data import pandas; df = pd.DataFrame()"],
)
def _python(action: str = "", code: str = "", **params) -> str:
    """Proxy to tools/python.py.

    Maps CLI action names to the python tool's `action` parameter.
    The python tool signature is:
        python(action="", code="", trace_id="", timeout=-1, json_schema="")

    Unknown CLI actions pass through unchanged (the python tool will return
    an "Unknown action" error for invalid values, which is the desired
    behaviour).
    """
    from tools.python import python

    # Map CLI action names to python tool action names.
    # - "run"  → "run"       (execute code)
    # - "calc" → "eval"      (evaluate expression, return result)
    # - "data" → "run_data"  (data analysis with pandas/matplotlib output)
    action_map = {
        "run": "run",
        "calc": "eval",
        "data": "run_data",
    }
    effective_action = action_map.get(action, action)

    r = python(action=effective_action, code=code)
    if not isinstance(r, dict):
        return str(r)
    return r.get("output", r.get("error", str(r)))
