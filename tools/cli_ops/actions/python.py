"""Python execution proxy for cli meta-tool.

Lazy imports python tool.
All functions auto-register via @register_action decorator.

NOTE: action names map to python modes:
  - "run"  → mode="run" (default, execute code)
  - "calc" → mode="run" (calculations are just code execution)
  - "data" → mode="run" (data analysis is just code execution)

Future AIs: if python gains distinct modes (e.g., "calc" returns
only the result without print output), update the mapping below.
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
def _python(action: str = "", code: str = "", mode: str = "run", **params) -> str:
    """Proxy to tools/python.py.

    Maps CLI action names to python modes. Currently all actions
    use mode="run" since python does not differentiate execution
    modes. The action parameter is preserved for future mode mapping.
    """
    from tools.python import python

    # Map action names to python modes.
    # Currently all map to "run" — update if python gains modes.
    mode_map = {
        "run": "run",
        "calc": "run",
        "data": "run",
    }
    effective_mode = mode_map.get(action, mode)

    r = python(mode=effective_mode, code=code)
    if not isinstance(r, dict):
        return str(r)
    return r.get("output", r.get("error", str(r)))
