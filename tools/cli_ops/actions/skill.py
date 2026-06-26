"""Skill dispatcher proxy for cli meta-tool.

Routes to skills/dispatcher.py skill() function.
All functions auto-register via @register_action decorator.

NOTE: Parameter mapping is hardcoded for the b3_api domain:
  query → arg becomes ticker=
  sync  → arg becomes files=
  status → arg is ignored

This is domain-specific coupling. Future AIs: if adding new skill
 domains, generalize the parameter mapping or move it to the skill
dispatcher itself.
"""
from __future__ import annotations

import json
from typing import Any

from tools.cli_ops._registry import register_action


@register_action(
    "skill", "call",
    help_text="Call a skill domain (shortcut: 'skill <domain> <mode> [arg]').",
    examples=[
        "skill b3_api status",
        "skill b3_api query PETR4",
        "skill b3_api sync files.csv",
    ],
)
def _skill_call(
    action: str = "",
    domain: str = "",
    mode: str = "",
    arg: str = "",
    **extra: Any,
) -> str:
    """Route to skills/dispatcher.py skill() function.

    arg interpretation by mode (hardcoded for b3_api):
        query -> arg becomes ticker=
        sync  -> arg becomes files=
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
