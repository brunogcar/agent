"""
registry.py -- Auto-discovery tool registration.

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


def register_all_tools(mcp: FastMCP) -> int:
    """
    Discover and register all @tool-decorated functions in the tools/ package.
    Returns the count of registered tools.
    All output goes to stderr -- never stdout.
    """
    import tools  # the tools package

    registered = 0
    errors: list[str] = []

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
                    registered += 1
                except Exception as e:
                    errors.append(f"Failed to register {full_name}.{attr_name}: {e}")

    # stderr only -- never stdout
    if errors:
        for err in errors:
            print(f"[registry] WARNING: {err}", file=sys.stderr)

    print(f"[registry] Registered {registered} tools from tools/", file=sys.stderr)
    return registered
