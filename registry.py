"""registry.py -- Auto-discovery tool registration.

CRITICAL: All output must go to stderr only.
stdout is the MCP stdio protocol channel -- any print() to stdout
before or during mcp.run() corrupts the JSON-RPC framing.

Scans tools/ for any function decorated with @tool and registers it
with FastMCP automatically. Adding a new tool requires zero changes
to server.py or this file -- just decorate the function.

Usage in tool files:
 from registry import tool

 @tool
 def web(action: str, query: str = "") -> dict:
     ...


[DESIGN] KEY DECISIONS — read before modifying:

  1. SCAN DEPTH IS ONE LEVEL for tools/: tools/*.py only, NOT tools/*_ops/ subpackages.
     Subpackages are imported INDIRECTLY — the facade (tools/git.py) imports its
     *_ops package, which triggers __init__.py auto-discovery and populates DISPATCH
     before @meta_tool runs. DO NOT add recursive scanning of tools/ — it would
     import action modules before their DISPATCH exists, and pull ChromaDB at MCP startup.

  2. skills/ IS scanned at the TOP LEVEL ONLY (flat modules in skills/).
     Only skills/dispatcher.py is expected to have @tool here.
     Sub-packages (skills/b3/, skills/news/, etc.) are SKIPPED (is_pkg check at line 136).
     The dispatcher imports them internally via its own domain discovery mechanism.
     DO NOT scan skills/ sub-packages — it would trigger ChromaDB/requests imports
     before MCP handshake completes.

  3. get_tool_names() returns [] before register_all_tools() runs.
     health.py /tools endpoint handles this with a static fallback list (which itself
     is stale — missing cli/browser/tavily/consult/parallel as of Jun 2026).

  4. NEVER use 'tool' as a variable name in any file that imports from registry.
     It shadows the @tool decorator.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType
from typing import Any

from mcp.server.fastmcp import FastMCP


def tool(fn: Any) -> Any:
    """Decorator that marks a function as an MCP tool for auto-discovery."""
    fn._is_mcp_tool = True
    return fn


# [P1 FIX] Module-level cache for discovered tool names.
# Populated during register_all_tools() and consumed by get_tool_names().
# This avoids re-scanning modules just to get a list of names.
_registered_tool_names: list[str] = []

# [GIT UN-MULTIPLEX v1] Cache for registered tool function references.
# Used by get_tool_actions() to introspect @meta_tool-decorated tools.
_registered_tool_fns: dict[str, Any] = {}


def get_tool_names() -> list[str]:
    """
    Return the list of tool names discovered during registration.

    This is used by health.py /tools endpoint to report the actual
    registered tools instead of a hardcoded list that drifts.

    If called before register_all_tools() has run, returns an empty list.
    In that case, the caller should fall back to a static list.
    """
    return list(_registered_tool_names)


def get_tool_actions(tool_name: str) -> list[str]:
    """
    Return action names for a @meta_tool-decorated tool.

    Looks up the registered function by name and reads its
    __tool_metadata__["actions"] list. Returns [] for non-meta
    tools or unknown tools (never raises).

    Used by the router to auto-generate tool capability lists
    without hardcoding action names.
    """
    fn = _registered_tool_fns.get(tool_name)
    if fn is None:
        return []
    return getattr(fn, "__tool_metadata__", {}).get("actions", [])


def register_all_tools(mcp: FastMCP) -> int:
    """
    Discover and register all @tool-decorated functions in tools/ and skills/.
    Returns the count of registered tools.
    All output goes to stderr -- never stdout.

    SCANNING RULES
    --------------
    tools/ -- scanned recursively one level (flat package).
    Every module is imported; every @tool function is registered.

    skills/ -- scanned at the TOP LEVEL ONLY (flat modules in skills/).
    Only skills/dispatcher.py is expected to have @tool here.
    Sub-packages (skills/b3/, skills/news/, etc.) are pure Python
    modules -- they are NOT scanned directly. The dispatcher imports
    them internally via its own domain discovery mechanism.

    DECISION: skills/ sub-packages are not scanned by registry
    skills/b3/__init__.py has no @tool. Only skills/dispatcher.py does.
    Scanning sub-packages would import domain modules at startup (slow,
    and triggers ChromaDB/requests imports before MCP handshake completes).
    The dispatcher uses lazy imports via importlib at call time instead.

    DECISION: skills/ scan is separate from tools/ scan
    Keeping them separate makes the log output clear ("tools/" vs "skills/")
    and lets us apply different scanning rules to each package independently.
    """
    global _registered_tool_names, _registered_tool_fns
    _registered_tool_names = []  # Reset on each registration call
    _registered_tool_fns = {}
    registered = 0
    errors: list[str] = []

    # ── Scan tools/ ──────────────────────────────────────────────────────────
    import tools
    for finder, module_name, _ in pkgutil.iter_modules(tools.__path__):
        full_name = f"tools.{module_name}"
        try:
            module: ModuleType = importlib.import_module(full_name)
        except Exception as e:
            errors.append(f"Failed to import {full_name}: {e}")
            continue

        for attr_name in dir(module):
            fn = getattr(module, attr_name)
            if callable(fn) and getattr(fn, "_is_mcp_tool", False):
                try:
                    mcp.tool()(fn)
                    _registered_tool_names.append(attr_name)
                    _registered_tool_fns[attr_name] = fn
                    registered += 1
                except Exception as e:
                    errors.append(f"Failed to register {full_name}.{attr_name}: {e}")

    # ── Scan skills/ (top-level flat modules only) ────────────────────────────
    # Only imports modules directly in skills/ (not sub-packages like skills/b3/).
    # dispatcher.py lives here and is the sole @tool entry point for all skills.
    try:
        import skills
        for finder, module_name, is_pkg in pkgutil.iter_modules(skills.__path__):
            if is_pkg:
                # Sub-packages (b3/, news/, etc.) -- skip, dispatcher loads them
                continue
            full_name = f"skills.{module_name}"
            try:
                module = importlib.import_module(full_name)
            except Exception as e:
                errors.append(f"Failed to import {full_name}: {e}")
                continue

            for attr_name in dir(module):
                fn = getattr(module, attr_name)
                if callable(fn) and getattr(fn, "_is_mcp_tool", False):
                    try:
                        mcp.tool()(fn)
                        _registered_tool_names.append(attr_name)
                        _registered_tool_fns[attr_name] = fn
                        registered += 1
                    except Exception as e:
                        errors.append(f"Failed to register {full_name}.{attr_name}: {e}")

        print(f"[registry] Scanned skills/ for @tool functions", file=sys.stderr)
    except ImportError:
        # skills/ package doesn't exist yet -- not an error, just skip
        print("[registry] skills/ package not found, skipping", file=sys.stderr)

    # stderr only -- never stdout
    if errors:
        for err in errors:
            print(f"[registry] WARNING: {err}", file=sys.stderr)

    print(f"[registry] Registered {registered} tools total (tools/ + skills/)", file=sys.stderr)
    return registered
