"""core/db_wal.py — SQLite WAL mode setup for concurrent read/write.

[WebUI v1] Critical for the WebUI: concurrent reads (HTTP requests) +
background sync writes on the same SQLite files. Without WAL mode, sync
writes block UI reads and you get `database is locked` errors under load.

Sets on every DB at startup:
  PRAGMA journal_mode=WAL      — readers don't block writers (and vice versa)
  PRAGMA synchronous=NORMAL    — safe with WAL, ~2x faster than FULL
  PRAGMA busy_timeout=5000     — wait 5s on lock instead of immediate error
  PRAGMA foreign_keys=ON       — enforce FK constraints

WAL mode is persistent (stored in the DB header) — setting it once per DB
file is enough. This module is idempotent: re-running on an already-WAL
DB is a no-op.

Usage (call once at server startup, before any requests):
    from core.db_wal import enable_wal_on_all_dbs
    enabled, skipped, failed = enable_wal_on_all_dbs()
    print(f"[startup] WAL: {enabled} enabled, {skipped} already, {failed} failed")
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _set_wal_pragmas(db_path: Path) -> str:
    """Open the DB, set WAL + pragmas. Returns 'enabled' | 'already' | 'failed'.

    WAL mode is persistent — once set, it stays. We detect "already WAL" by
    reading journal_mode back; if it's already 'wal', we skip the PRAGMA
    (still set the other pragmas which are per-connection, not persistent).
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            cur = conn.execute("PRAGMA journal_mode")
            current = cur.fetchone()
            current_mode = current[0] if current else ""
            if str(current_mode).lower() != "wal":
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.commit()
            return "already" if str(current_mode).lower() == "wal" else "enabled"
        finally:
            conn.close()
    except Exception:
        return "failed"


def enable_wal_on_all_dbs(memory_root: Path | None = None) -> tuple[int, int, int]:
    """Enable WAL mode + pragmas on every SQLite DB under memory_root.

    Walks memory_db/ recursively, finds every *.db file, sets WAL pragmas.
    Idempotent — safe to call on every startup.

    Returns: (enabled_count, already_wal_count, failed_count)
    """
    from core.config import cfg
    root = memory_root or getattr(cfg, "memory_root", None)
    if not root:
        return (0, 0, 0)
    root = Path(root)
    if not root.exists():
        return (0, 0, 0)

    enabled = 0
    already = 0
    failed = 0
    for db_path in sorted(root.rglob("*.db")):
        result = _set_wal_pragmas(db_path)
        if result == "enabled":
            enabled += 1
        elif result == "already":
            already += 1
        else:
            failed += 1
    return (enabled, already, failed)


if __name__ == "__main__":
    # Manual test: python -m core.db_wal
    e, a, f = enable_wal_on_all_dbs()
    print(f"WAL: {e} enabled, {a} already WAL, {f} failed")
