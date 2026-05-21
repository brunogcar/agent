"""
python.py — Python execution proxy for cli meta-tool.

Lazy imports python_exec tool.
All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

from typing import Any

from tools.cli_ops._registry import register_action

@register_action("python", "run")
@register_action("python", "calc")
@register_action("python", "data")
def _python(code: str = "", mode: str = "run") -> str:
    """Proxy to tools/python_exec.py."""
    from tools.python_exec import python

    r = python(mode=mode, code=code)
    if not isinstance(r, dict):
        return str(r)
    return r.get("output", r.get("error", str(r)))