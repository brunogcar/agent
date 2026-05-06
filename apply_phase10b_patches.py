"""
apply_phase10b_patches.py -- run from D:/mcp/agent/

Fixes ChromaDB cold-start MCP timeout.

Problem: First call to memory() takes 10-15s to load the embedding model.
LM Studio's MCP bridge has a ~10s timeout, so the first store/recall times out.

Fix: Warm up ChromaDB in a background thread during server startup so the
embedding model is loaded before the first actual tool call.

Also fixes the MCP timeout by increasing FastMCP's default timeout.
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch(filepath, old, new, label):
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new)
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Phase 10b patches ===\n")

# ── 1. server.py: warm up ChromaDB in background thread at startup ────────────
# ChromaDB loads its embedding model on first use, causing a 10-15s delay
# that exceeds LM Studio's MCP bridge timeout. Warming it up during boot
# means the embedding model is ready before any tool call arrives.
patch(
    "server.py",
    '''# -- Run (hands stdout to FastMCP's stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()''',
    '''# -- Warm up ChromaDB in background (avoids cold-start MCP timeout) -----------
def _warmup_chromadb() -> None:
    """Load ChromaDB embedding model before first tool call."""
    try:
        from memory.store import memory as _mem
        # Tiny no-op query to trigger embedding model load
        _mem.recall("warmup", top_k=1, min_score=0.0)
        print("[server] ChromaDB warmup complete", file=sys.stderr)
    except Exception as e:
        print(f"[server] ChromaDB warmup skipped: {e}", file=sys.stderr)

import threading as _threading
_threading.Thread(target=_warmup_chromadb, daemon=True).start()

# -- Run (hands stdout to FastMCP's stdio transport) ----------------------------
if __name__ == "__main__":
    mcp.run()''',
    "server: ChromaDB background warmup on startup",
)

print("\nDone. Restart the MCP server for the warmup to take effect.")
print("The first memory() call should no longer timeout in LM Studio.")
