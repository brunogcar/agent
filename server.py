"""
server.py -- MCP Agent entrypoint.

stdout = MCP stdio protocol channel. NOTHING may print to stdout.
All diagnostics go to stderr or the log file.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def _fix_streams() -> None:
    """
    1. Force UTF-8 on both streams (Windows cp1252 crashes on non-ASCII).
    2. Replace stdout with a stderr-backed stream so any accidental
       print() calls during boot go to stderr instead of corrupting
       the MCP JSON-RPC protocol channel.
    """
    # Fix encoding first
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if hasattr(stream, "buffer") and (
            stream.encoding is None or stream.encoding.lower() != "utf-8"
        ):
            setattr(sys, name,
                    io.TextIOWrapper(stream.buffer, encoding="utf-8",
                                     errors="replace", line_buffering=True))

    # Redirect stdout -> stderr during boot so nothing corrupts the channel.
    # FastMCP.run() will reclaim stdout for the stdio transport.
    # We save the real stdout so FastMCP can restore it.
    sys._real_stdout = sys.stdout       # type: ignore[attr-defined]
    sys.stdout = sys.stderr             # boot-time stdout -> stderr


_fix_streams()

# -- Bootstrap sys.path -------------------------------------------------------
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

# -- Build the server (stdout still redirected to stderr here) ----------------
mcp = FastMCP("agent")
_tool_count = register_all_tools(mcp)

# -- Boot log (all goes to stderr via the redirect above) --------------------
_boot_tid = tracer.new_trace("startup", goal="server boot")
tracer.step(_boot_tid, "boot", "MCP Agent ready",
            tools=_tool_count,
            planner=cfg.planner_model,
            executor=cfg.executor_model,
            router=cfg.router_model)

_W = 56
print("", file=sys.stderr)
print("=" * _W, file=sys.stderr)
print("  MCP Agent Stack -- Ready".center(_W), file=sys.stderr)
print("=" * _W, file=sys.stderr)
print(f"  Tools     : {_tool_count}", file=sys.stderr)
print(f"  Planner   : {cfg.planner_model}", file=sys.stderr)
print(f"  Executor  : {cfg.executor_model}", file=sys.stderr)
print(f"  Router    : {cfg.router_model}", file=sys.stderr)
print(f"  Workspace : {cfg.workspace_root}", file=sys.stderr)
print(f"  Memory    : {cfg.memory_chroma_path}", file=sys.stderr)
print(f"  Env       : {cfg.env}", file=sys.stderr)
print("=" * _W, file=sys.stderr)
print("", file=sys.stderr)

tracer.finish(_boot_tid, success=True, result=f"{_tool_count} tools registered")

# -- Restore real stdout and hand it to FastMCP's stdio transport -------------
sys.stdout = sys._real_stdout           # type: ignore[attr-defined]

# -- Warm up ChromaDB in background (avoids cold-start MCP timeout) -----------
def _warmup_chromadb() -> None:
    """Load ChromaDB embedding model before first tool call."""
    try:
        from core.memory import memory as _mem
        # Tiny no-op query to trigger embedding model load
        _mem.recall("warmup", top_k=1, min_score=0.0)
        print("[server] ChromaDB warmup complete", file=sys.stderr)
    except Exception as e:
        print(f"[server] ChromaDB warmup skipped: {e}", file=sys.stderr)

import threading as _threading
_threading.Thread(target=_warmup_chromadb, daemon=True).start()

# -- Run (hands stdout to FastMCP's stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()

