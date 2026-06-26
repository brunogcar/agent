"""Python execution proxy for cli meta-tool.

Lazy imports python_exec tool.
All functions auto-register via @register_action decorator.
"""
from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "python", "run",
    help_text="Execute Python code (shortcut: 'run <code>' or 'exec <code>').",
    examples=["run print(\'hello\')", "exec 2+2"],
)
@register_action(
    "python", "calc",
    help_text="Calculate expression (shortcut: 'calc <expr>').",
    examples=["calc 2+2", "calc len([1,2,3])"],
)
@register_action(
    "python", "data",
    help_text="Run data analysis code.",
    examples=["data import pandas; df = pd.DataFrame()"],
)
def _python(action: str = "", code: str = "", mode: str = "run", **params) -> str:
    """Proxy to tools/python_exec.py."""
    from tools.python_exec import python

    r = python(mode=mode, code=code)
    if not isinstance(r, dict):
        return str(r)
    return r.get("output", r.get("error", str(r)))
