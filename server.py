"""
server.py -- MCP Agent entrypoint.

Minimal by design. All tool logic lives in tools/.
All configuration lives in core/config.py + .env.
All tools are auto-discovered by registry.py -- no manual wiring here.

Starting the server:
    python server.py

The server exposes 8 meta-tools to any MCP client:
    web, python, file, git, memory, agent, notify, visualize

Protected files (autocode will never touch these):
    server.py, registry.py, core/config.py, core/tracer.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def _force_utf8() -> None:
    """
    Force UTF-8 on stdout and stderr.
    Windows defaults to cp1252 which crashes on any non-ASCII character.
    MCP clients read stderr -- a crash here kills the connection before tools load.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "buffer") and (
            stream.encoding is None or stream.encoding.lower() != "utf-8"
        ):
            setattr(
                sys, stream_name,
                io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"),
            )


_force_utf8()

# -- Bootstrap: ensure agent root is on sys.path ------------------------------
# Allows `from core.config import cfg` to work regardless of working directory
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# -- Core imports (order matters) ---------------------------------------------
from core.config import cfg      # loads .env, builds all paths
from core.tracer import tracer   # structured logging

# Ensure all required directories exist before anything else
cfg.ensure_dirs()

# -- MCP framework ------------------------------------------------------------
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

# -- Boot trace ---------------------------------------------------------------
_boot_tid = tracer.new_trace("startup", goal="server boot")

# -- Create MCP server and register all tools ---------------------------------
mcp = FastMCP("agent")
_tool_count = register_all_tools(mcp)

# -- Startup log --------------------------------------------------------------
tracer.step(_boot_tid, "boot", "MCP Agent ready",
            tools=_tool_count,
            planner=cfg.planner_model,
            executor=cfg.executor_model,
            router=cfg.router_model,
            memory=str(cfg.memory_chroma_path),
            workspace=str(cfg.workspace_root))

# ASCII-safe banner (no box-drawing chars -- cp1252 and some MCP clients crash)
_W = 56
print("\n" + "=" * _W)
print("  MCP Agent Stack -- Ready".center(_W))
print("=" * _W)
print(f"  Tools     : {_tool_count}")
print(f"  Planner   : {cfg.planner_model}")
print(f"  Executor  : {cfg.executor_model}")
print(f"  Router    : {cfg.router_model}")
print(f"  Workspace : {cfg.workspace_root}")
print(f"  Memory    : {cfg.memory_chroma_path}")
print(f"  Env       : {cfg.env}")
print("=" * _W + "\n")

tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")

# -- Run ----------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
