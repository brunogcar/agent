"""webui.py — Single-process WebUI entry point.

[WebUI v1] One command boots the whole thing:
    python webui.py

Architecture (per LLM review consensus):
  - Extends the existing FastAPI gateway (one process, one port)
  - Jinja2 + HTMX + Alpine.js + Chart.js (no SPA, no build step)
  - Direct skill engine imports (NOT through the MCP dispatcher)
  - SSE for sync progress (NOT WebSocket)
  - CSS variables for themes (3-layer token system)
  - JSON files for i18n (NOT gettext)
  - SQLite WAL mode for concurrent read/write

The WebUI routes are mounted at /webui/* and /api/webui/* on the same
FastAPI app that serves /chat, /task, /ws (the existing MCP gateway).
LM Studio / Claude Desktop continue to use server.py (MCP stdio) —
they're unaffected.

Usage:
    python webui.py                      # default port 8000, host 127.0.0.1
    python webui.py --port 7860          # custom port
    python webui.py --host 0.0.0.0       # LAN access
    python webui.py --reload             # dev mode (auto-restart on file change)
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Bootstrap sys.path (same as server.py) ──────────────────────────────────
_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Brazilian Financial Data WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Dev mode: auto-restart on file change")
    parser.add_argument("--no-sync", action="store_true", help="Skip startup freshness check / auto-sync")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn fastapi", file=sys.stderr)
        raise SystemExit(1)

    # ── Critical: SQLite WAL mode BEFORE any request ────────────────────────
    # Concurrent reads (WebUI) + background sync writes need WAL or you get
    # `database is locked`. Idempotent — safe to run on every startup.
    try:
        from core.db_wal import enable_wal_on_all_dbs
        enabled, already, failed = enable_wal_on_all_dbs()
        print(f"[startup] SQLite WAL: {enabled} enabled, {already} already WAL, {failed} failed",
              file=sys.stderr)
        if failed:
            print(f"[startup] WARNING: {failed} DBs failed WAL setup (may be read-only or locked)",
                  file=sys.stderr)
    except Exception as e:
        print(f"[startup] WARNING: WAL setup failed: {e}", file=sys.stderr)

    # ── Launch ──────────────────────────────────────────────────────────────
    print(f"[startup] WebUI on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"[startup] Docs:   http://{args.host}:{args.port}/docs", file=sys.stderr)
    print(f"[startup] WebUI:  http://{args.host}:{args.port}/webui", file=sys.stderr)
    print(f"[startup] Sync on startup: {'disabled' if args.no_sync else 'enabled'}", file=sys.stderr)

    uvicorn.run(
        "webui.app:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
