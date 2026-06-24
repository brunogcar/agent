"""
tools/_meta_tool.py — @meta_tool decorator for auto-generated Literal enums and docstrings.

Auto-generates FastMCP-compatible action: Literal[...] type annotations and docstrings
from a DISPATCH dict. Designed for meta-tools (git, browser, file, web) that route actions
to handler functions via a central dispatch table.

Usage:
    from tools._meta_tool import meta_tool
    from tools.git_ops._registry import DISPATCH

    @tool
    @meta_tool(DISPATCH["git"], doc_sections=[
        "IMPORTANT — root vs path parameter:",
        ' root — the repo directory: "agent" (default) | "workspace" | "/absolute/path"',
        ' path — ONLY used by diff to filter a specific file. NOT the repo directory.',
        "Commands intentionally excluded from autonomous execution:",
        " fetch, pull, merge, rebase, push",
    ])
    def git(action: str = "", ...) -> dict:
        ...

Key design decisions (for future AI auditors):
- WHY eval(): Python's typing.Literal requires literal values at parse time.
  No dynamic construction exists in the standard library. eval() is the only
  reliable way, and it's safe because we only eval strings we construct from
  known DISPATCH keys validated by ^[a-z][a-z0-9_]*$.

  NOTE: eval() runs in a restricted namespace with only Literal and no builtins.
  The expression is structurally a type construction (Literal["a", "b"]), not
  executable code. The regex validates all keys before construction.

- WHY return fn directly (no wrapper): @tool is a marker decorator that sets
  fn._is_mcp_tool = True and returns fn unchanged. If we return a wrapper,
  @tool marks the wrapper — but the wrapper might not preserve mutated
  __annotations__ through functools.wraps in all Python versions. Returning fn
  directly is zero-risk.

- WHY del fn.__signature__: inspect.signature() caches results per-function-object.
  If the function was previously inspected (e.g., by @tool or by import-time code),
  the cached signature won't reflect our __annotations__ mutation. Deleting
  the cache forces re-derivation from the new annotations.

- DECORATOR ORDER MATTERS: @meta_tool must be INNER (closest to function).
  It mutates __annotations__ and __doc__ in place. @tool must be OUTER.
  If a future decorator uses functools.wraps (creating a wrapper callable),
  @meta_tool must run BEFORE that wrapper is created, or the wrapper's
  __annotations__ won't reflect the Literal mutation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def meta_tool(dispatch: Dict[str, Any], doc_sections: List[str] | None = None):
    """
    Decorator that patches a meta-tool function's __annotations__ and __doc__
    from a DISPATCH dict.

    Args:
        dispatch: Dict mapping action_name -> handler metadata dict.
                  Must have keys like {"status": {"func": ..., "help": ...}, ...}
        doc_sections: Optional list of strings to append to the generated docstring
                      after the action list. Use for tool-specific usage notes,
                      parameter semantics, excluded commands, etc.

    Returns:
        The original function object, mutated in place.
    """
    def decorator(fn: Any) -> Any:
        # ── 1. Validate dispatch is non-empty ─────────────────────────────
        if not dispatch:
            raise ValueError(
                f"@meta_tool received empty dispatch for {fn.__name__!r}. "
                "Import order bug: action modules must be imported before the tool facade."
            )

        # ── 2. Extract and validate action names ──────────────────────────
        actions = sorted(dispatch.keys())
        for name in actions:
            if not re.match(r"^[a-z][a-z0-9_]*$", name):
                raise ValueError(
                    f"Invalid action name {name!r} in DISPATCH for {fn.__name__!r}. "
                    f"Must match ^[a-z][a-z0-9_]*$."
                )

        # ── 3. Build Literal type via eval() ──────────────────────────────
        #    Literal requires literal values at parse time. No dynamic
        #    construction exists in stdlib. eval() is safe here because we
        #    only eval strings we construct from validated DISPATCH keys.
        #    We use a restricted namespace with only Literal and no builtins.
        from typing import Literal
        args_str = ", ".join(f'"{a}"' for a in actions)
        literal_expr = f"Literal[{args_str}]"
        ActionLiteral = eval(literal_expr, {"Literal": Literal, "__builtins__": {}})

        # ── 4. Patch __annotations__ ──────────────────────────────────────
        #    Replace action: str with action: Literal["a", "b", ...]
        if "action" in fn.__annotations__:
            fn.__annotations__["action"] = ActionLiteral

        # ── 5. Delete cached signature to force re-derivation ─────────────
        #    inspect.signature() caches results per-function-object.
        #    Stale cache won't reflect our annotation mutation.
        if hasattr(fn, "__signature__"):
            del fn.__signature__

        # ── 6. Build docstring from DISPATCH metadata ───────────────────────
        lines = [
            f"{fn.__name__} meta-tool — atomic actions.",
            "",
            f"action: {' | '.join(actions)}",
            "",
        ]
        for name in actions:
            info = dispatch[name]
            lines.append(info.get("help", f"{name}").strip())
            exs = info.get("examples", [])
            if exs:
                lines.append(" Examples: ")
                for ex in exs:
                    lines.append(f"  {ex}")
                lines.append("")

        # Append tool-specific doc sections (usage notes, param semantics, etc.)
        if doc_sections:
            lines.append("")
            for section in doc_sections:
                lines.append(section)

        fn.__doc__ = "\n".join(lines)

        # ── 7. Store metadata for registry introspection ────────────────────
        fn.__tool_metadata__ = {
            "actions": actions,
            "dispatch": {k: {
                "help": v.get("help", ""),
                "needs_repo": v.get("needs_repo", False),
                "examples": v.get("examples", []),
            } for k, v in dispatch.items()},
        }

        return fn
    return decorator
