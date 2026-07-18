"""Skill dispatcher proxy for cli meta-tool.

Routes to skills/dispatcher.py skill() function.
All functions auto-register via @register_action decorator.

[v1.2] Parameter mapping is generic: `arg` is passed as a generic
positional parameter, and any extra kwargs from the caller are passed
through unchanged. The skill dispatcher interprets `arg` based on the
domain + mode (domain-specific logic lives in the dispatcher, not here).

Backward compat: callers can still pass domain-specific kwargs via the
CLI (e.g., `skill b3_api query ticker=PETR4`); these flow through
**extra and are forwarded to the dispatcher alongside the generic `arg`.
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

    `arg` is passed as a generic positional parameter. The skill
    dispatcher interprets it based on the domain + mode (domain-specific
    logic lives in the dispatcher, not here).

    Callers can also pass domain-specific kwargs via the CLI (e.g.,
    `skill b3_api query ticker=PETR4`); these are forwarded via **extra
    alongside the generic `arg`. This preserves backward compat for
    any caller that already passes named parameters.
    """
    try:
        from skills.dispatcher import skill as _skill_fn

        kwargs: dict[str, Any] = {}
        if arg:
            # Pass arg as a generic parameter. The dispatcher decides
            # what to do with it based on domain + mode.
            kwargs["arg"] = arg
        # Pass through any extra params from the caller (domain-specific).
        # This preserves backward compat for callers that pass named
        # parameters like ticker= or files=.
        kwargs.update(extra)

        result = _skill_fn(domain=domain, mode=mode, **kwargs)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)
    except ImportError:
        return "skills/dispatcher.py not found -- ensure skills/ package is installed"
    except Exception as e:
        return f"skill error: {e}"
