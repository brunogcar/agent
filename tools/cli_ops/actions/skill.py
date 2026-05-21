"""
skill.py — Skill dispatcher proxy for cli meta-tool.

Routes to skills/dispatcher.py skill() function.
All functions auto-register via @register_action decorator.
"""

from __future__ import annotations

import json
from typing import Any

from tools.cli_ops.actions._registry import register_action

@register_action("skill", "call")
def _skill_call(domain: str = "", mode: str = "", arg: str = "", **extra: Any) -> str:
    """
    Route to skills/dispatcher.py skill() function.

    arg interpretation by mode:
      query  -> arg becomes ticker=
      sync   -> arg becomes files=
      status -> arg ignored
    """
    try:
        from skills.dispatcher import skill as _skill_fn

        kwargs: dict[str, Any] = {}
        if arg:
            if mode == "query":
                kwargs["ticker"] = arg.upper()
            elif mode == "sync":
                kwargs["files"] = arg

        result = _skill_fn(domain=domain, mode=mode, **kwargs)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)
    except ImportError:
        return "skills/dispatcher.py not found -- ensure skills/ package is installed"
    except Exception as e:
        return f"skill error: {e}"