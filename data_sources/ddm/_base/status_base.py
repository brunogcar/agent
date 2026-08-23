"""data_sources/ddm/_base/status_base.py -- Shared status-reporter scaffold.

All 7 DDM status_reporter.py files share an identical outer scaffold:

    path = db_path()
    if not path.exists():
        return {"status": "not_synced", "message": "<src>.db not found. ..."}
    try:
        conn = connect(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced", "message": "<src>.db not found."}
    try:
        # ... source-specific queries that build the status dict ...
        return {...}
    except Exception:
        return {"status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all."}
    finally:
        conn.close()

Only the middle "source-specific queries" block differs (4 distinct query
patterns: multi-page per-index loop, acoes minimal, dividends by-tipo,
fluxo date-range, focus year/indicator counts).

This module provides a `BaseDDMStatusReporter` class that handles the
path-check + connect + try/except + finally scaffold. Each source's
status_reporter.py subclasses it and implements `_build_status_dict(conn,
path, db_size_kb)` with its source-specific queries.

[Phase 3, Commit 1] Extracted from the 7 status_reporter.py files.
"""

from __future__ import annotations


class BaseDDMStatusReporter:
    """Base class with the shared status() try/except/finally scaffold.

    Subclasses set:
        SOURCE_NAME: str  -- e.g. "inflation" (for the not_synced message).

    Subclasses implement:
        _build_status_dict(conn, path, db_size_kb) -> dict
            Run the source-specific queries against `conn` and return the
            full status dict (including "status": "ok"). The base class
            handles the path-check + connect + try/except + finally.

    The `db_path_fn` and `connect_fn` are passed in to `status()` so the
    subclass doesn't need to import them at class-load time (avoids
    circular imports with the per-source catalog module).
    """

    SOURCE_NAME: str = ""

    @classmethod
    def status(cls, db_path_fn, connect_fn) -> dict:
        """Return a status dict for the source's DB.

        Args:
            db_path_fn: callable() -> Path (the per-source catalog.db_path).
            connect_fn: callable(read_only=True) -> sqlite3.Connection.

        Returns one of:
            {"status": "not_synced", "message": "..."} -- DB missing.
            {"status": "ok", "path": ..., "db_size_kb": ..., ...source...}
            {"status": "not_synced",
             "message": "DB exists but tables not created. Run sync_all."}
        """
        source_name = cls.SOURCE_NAME
        path = db_path_fn()
        if not path.exists():
            return {
                "status": "not_synced",
                "message": f"{source_name}.db not found. Run sync_all first.",
            }

        try:
            conn = connect_fn(read_only=True)
        except FileNotFoundError:
            return {
                "status": "not_synced",
                "message": f"{source_name}.db not found.",
            }

        try:
            db_size_kb = round(path.stat().st_size / 1024, 1)
            return cls._build_status_dict(conn, path, db_size_kb)
        except Exception:
            return {
                "status": "not_synced",
                "message": "DB exists but tables not created. Run sync_all.",
            }
        finally:
            conn.close()

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb: float) -> dict:
        """Run the source-specific queries and return the status dict.

        Subclasses MUST override this. The base implementation returns a
        minimal "ok" dict (used only as a safety fallback).
        """
        return {
            "status": "ok",
            "path": str(path),
            "db_size_kb": db_size_kb,
        }
