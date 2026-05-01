"""
server.py — MCP Agent entrypoint.

Minimal by design. All tool logic lives in tools/.
All configuration lives in core/config.py + .env.
All tools are auto-discovered by registry.py — no manual wiring here.

Starting the server:
    python server.py

The server exposes 8 meta-tools to any MCP client:
    web · python · file · git · memory · agent · notify · visualize

Protected files (autocode will never touch these):
    server.py · registry.py · core/config.py · core/tracer.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Bootstrap — ensure agent root is on sys.path ──────────────────────────────
# Allows `from core.config import cfg` to work regardless of working directory
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# ── Core imports — order matters ──────────────────────────────────────────────
from core.config import cfg          # loads .env, builds all paths
from core.tracer import tracer       # structured logging, must come before tools

# Ensure all required directories exist before anything else
cfg.ensure_dirs()

# ── MCP framework ─────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

# ── Boot trace ────────────────────────────────────────────────────────────────
_boot_tid = tracer.new_trace("startup", goal="server boot")

# ── Create MCP server and register all tools ──────────────────────────────────
mcp = FastMCP("agent")
_tool_count = register_all_tools(mcp)

# ── Startup summary ───────────────────────────────────────────────────────────
tracer.step(_boot_tid, "boot", "MCP Agent ready",
            tools=_tool_count,
            planner=cfg.planner_model,
            executor=cfg.executor_model,
            router=cfg.router_model,
            memory=str(cfg.memory_chroma_path),
            workspace=str(cfg.workspace_root))

_BANNER = f"""
╔══════════════════════════════════════════════════════╗
║              MCP Agent Stack — Ready                 ║
╠══════════════════════════════════════════════════════╣
║  Tools      : {_tool_count:<38}║
║  Planner    : {cfg.planner_model:<38}║
║  Executor   : {cfg.executor_model:<38}║
║  Router     : {cfg.router_model:<38}║
║  Memory     : {str(cfg.memory_chroma_path):<38}║
║  Workspace  : {str(cfg.workspace_root):<38}║
║  Env        : {cfg.env:<38}║
╚══════════════════════════════════════════════════════╝
"""
print(_BANNER)

tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
