"""
server.py -- MCP Agent entrypoint.

Minimal by design. All tool logic lives in tools/.
All configuration lives in core/config.py + .env.
All tools are auto-discovered by registry.py -- no manual wiring here.

IMPORTANT: stdout is the MCP protocol channel (stdio transport).
           Never print to stdout before or during mcp.run().
           All diagnostics go to stderr only.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def _force_utf8() -> None:
    """Force UTF-8 on stdout/stderr. Windows cp1252 crashes on non-ASCII."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if hasattr(stream, "buffer") and (
            stream.encoding is None or stream.encoding.lower() != "utf-8"
        ):
            setattr(sys, name,
                    io.TextIOWrapper(stream.buffer, encoding="utf-8",
                                     errors="replace", line_buffering=True))


_force_utf8()

# -- Bootstrap: ensure agent root is on sys.path ------------------------------
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# -- Core imports -------------------------------------------------------------
from core.config import cfg
from core.tracer import tracer

cfg.ensure_dirs()

# -- MCP framework ------------------------------------------------------------
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

# -- Build server (no stdout output here -- stdio transport not yet started) --
mcp = FastMCP("agent")
_tool_count = register_all_tools(mcp)

# -- Boot summary to STDERR only (stdout = MCP protocol channel) --------------
_boot_tid = tracer.new_trace("startup", goal="server boot")
tracer.step(_boot_tid, "boot", "MCP Agent ready",
            tools=_tool_count,
            planner=cfg.planner_model,
            executor=cfg.executor_model,
            router=cfg.router_model)

_W = 56
_banner = "\n".join([
    "",
    "=" * _W,
    "  MCP Agent Stack -- Ready".center(_W),
    "=" * _W,
    f"  Tools     : {_tool_count}",
    f"  Planner   : {cfg.planner_model}",
    f"  Executor  : {cfg.executor_model}",
    f"  Router    : {cfg.router_model}",
    f"  Workspace : {cfg.workspace_root}",
    f"  Memory    : {cfg.memory_chroma_path}",
    f"  Env       : {cfg.env}",
    "=" * _W,
    "",
])

# stderr only -- stdout is reserved for MCP stdio protocol
print(_banner, file=sys.stderr)
tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")

# -- Run (hands stdout to FastMCP stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()
