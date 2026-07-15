"""Type registry for workflow_ops — the SECOND-level dispatch.

While _registry.py holds the META-level dispatch (what to do: run, list,
status, cancel, history), THIS module holds the WORKFLOW-TYPE-level dispatch
(which workflow to run: research, data, autocode, deep_research, understand,
autoresearch, auto).

The two-level split means:
  - `workflow(action="run", type="research", ...)`  → ACTION_DISPATCH["run"]
                                                       → TYPE_DISPATCH["research"]
  - `workflow(action="list")`                       → ACTION_DISPATCH["list"]
  - `workflow(action="status", trace_id=...)`       → ACTION_DISPATCH["status"]

TYPE_DISPATCH is a flat dict (NOT nested under tool_name) because there is
only one workflow tool — no need for a tool_name key. Each entry maps a
type_name to {"func": handler, "help": help_text}.

[DESIGN] KEY INVARIANTS — read before modifying:
  1. TYPE_DISPATCH is module-level. All type modules share the same dict
     instance via the `from ... import TYPE_DISPATCH` re-export pattern.
  2. Duplicate registration raises ValueError loudly.
  3. The `func` reference is the raw callable — invoked with explicit kwargs
     by the run action handler.
  4. Type handlers receive ALL the workflow-tool kwargs (goal, code,
     target_file, mode, error_msg, feature_desc, files, git_diff, dry_run,
     project_root, trace_id, resume) and pick what they need via **kwargs.
     This keeps the signature uniform across handlers and lets the run action
     forward every kwarg without conditional branches.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional

TYPE_DISPATCH: Dict[str, Dict[str, Any]] = {}


def register_type(
    type_name: str,
    help_text: str = "",
) -> Callable:
    """Decorator that registers a type handler under TYPE_DISPATCH[type_name].

    Args:
        type_name: Workflow type key (e.g. "research", "data", "autocode").
                   Must match ^[a-z][a-z0-9_]*$ — same pattern as actions.
        help_text: Human-readable description of the workflow type.

    Returns:
        The original function unchanged (decorator is registration-only).
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if type_name in TYPE_DISPATCH:
            raise ValueError(
                f"Duplicate type registration: '{type_name}' already exists "
                f"in TYPE_DISPATCH."
            )
        TYPE_DISPATCH[type_name] = {
            "func": func,
            "help": help_text,
        }
        return func
    return decorator
