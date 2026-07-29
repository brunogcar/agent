"""skills/cvm/_freshness.py — Data freshness helper for CVM skills.

Checks the sync_state table in each CVM/B3 database and returns the last
sync timestamp. Used by all CVM skills to expose `data_freshness` in their
responses so consumers know data age.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _check_db_freshness(db_path: Path, table: str = "sync_state") -> str:
    """Check the last sync timestamp in a database's sync_state table.

    Returns ISO timestamp string, or "" if not available.
    """
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Try common column names for the timestamp
        for col in ("synced_at", "last_sync", "sync_at", "dt_sync"):
            try:
                row = conn.execute(
                    f"SELECT {col} as ts FROM {table} ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                if row and row["ts"]:
                    conn.close()
                    return str(row["ts"])
            except sqlite3.OperationalError:
                continue
        conn.close()
    except Exception:
        pass
    return ""


def get_freshness() -> dict[str, str]:
    """Get last-sync timestamps for all CVM/B3 databases.

    Returns: {"dfp": "2026-07-24T...", "itr": "...", "fre": "...", ...}
    Missing/unsynced DBs return "".
    """
    from data_sources.cvm._db import (
        dfp_db_path, itr_db_path, fre_db_path, ipe_db_path, cad_db_path, vlmo_db_path, cgvn_db_path, fca_db_path,
    )
    from data_sources.cvm._db import bridge_db_path as bridge_path
    from data_sources.b3.dividends.catalog import db_path as b3_div_path
    from data_sources.b3.cotahist.catalog import db_path as cotahist_path

    result: dict[str, str] = {}

    # CVM databases — sync_state table
    for name, path_fn in [
        ("dfp", dfp_db_path),
        ("itr", itr_db_path),
        ("fre", fre_db_path),
        ("ipe", ipe_db_path),
        ("cad", cad_db_path),
        ("vlmo", vlmo_db_path),
        ("cgvn", cgvn_db_path),
        ("fca", fca_db_path),
    ]:
        try:
            result[name] = _check_db_freshness(path_fn())
        except Exception:
            result[name] = ""

    # Bridge — sync_log table
    try:
        bp = bridge_path()
        if bp.exists():
            conn = sqlite3.connect(f"file:{bp}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT synced_at FROM sync_log ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            result["bridge"] = str(row["ts"]) if row and row["synced_at"] else ""
            conn.close()
        else:
            result["bridge"] = ""
    except Exception:
        result["bridge"] = ""

    # B3 dividends — sync_state table
    try:
        result["b3_dividends"] = _check_db_freshness(b3_div_path())
    except Exception:
        result["b3_dividends"] = ""

    # COTAHIST — no sync_state table; use max(refdate) from cotahist
    try:
        cp = cotahist_path()
        if cp.exists():
            conn = sqlite3.connect(f"file:{cp}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT MAX(refdate) as max_date FROM cotahist"
            ).fetchone()
            result["cotahist"] = str(row["max_date"]) if row and row["max_date"] else ""
            conn.close()
        else:
            result["cotahist"] = ""
    except Exception:
        result["cotahist"] = ""

    return result


def get_last_synced_period() -> dict[str, str]:
    """Get the last data period (``data_fim_exerc``) available in each database.

    This complements :func:`get_freshness` (which returns *when* each DB was
    last synced) by reporting *which fiscal period* is the most recent
    available in each DB. For DFP this is the latest year-end (e.g.
    ``"2023-12-31"``); for ITR this is the latest quarter-end (e.g.
    ``"2024-06-30"``).

    Returns:
        ``{"dfp": "2023-12-31", "itr": "2024-06-30", ...}`` — one entry per
        CVM database that has a ``contas`` table. Missing / unsynced / unreadable
        DBs return ``""``.
    """
    from data_sources.cvm._db import (
        dfp_db_path, itr_db_path, fre_db_path, ipe_db_path,
        cad_db_path, vlmo_db_path, cgvn_db_path, fca_db_path,
    )

    result: dict[str, str] = {}
    for name, path_fn in [
        ("dfp", dfp_db_path),
        ("itr", itr_db_path),
        ("fre", fre_db_path),
        ("ipe", ipe_db_path),
        ("cad", cad_db_path),
        ("vlmo", vlmo_db_path),
        ("cgvn", cgvn_db_path),
        ("fca", fca_db_path),
    ]:
        try:
            p = path_fn()
            if not p.exists():
                result[name] = ""
                continue
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            # The contas table holds all financial-statement line items with
            # data_fim_exerc as the period-end date. MAX(data_fim_exerc) is
            # the most recent period present in the DB. The query is wrapped
            # in a try/except OperationalError because some CVM DBs (e.g.
            # cad, ipe) may not have a `contas` table at all — those return "".
            try:
                row = conn.execute(
                    "SELECT MAX(data_fim_exerc) as max_date FROM contas"
                ).fetchone()
                result[name] = str(row["max_date"]) if row and row["max_date"] else ""
            except sqlite3.OperationalError:
                # No `contas` table in this DB (e.g. cad / ipe / vlmo / cgvn
                # / fca are registers, not financial-statement databases).
                result[name] = ""
            conn.close()
        except Exception:
            result[name] = ""
    return result


def add_freshness(result: dict) -> dict:
    """Add data_freshness + last_synced_period to a skill result dict (in-place + return).

    Usage at the end of a skill function:
        from skills.cvm._freshness import add_freshness
        return add_freshness(my_result)
    """
    try:
        result["data_freshness"] = get_freshness()
    except Exception:
        result["data_freshness"] = {}
    try:
        result["last_synced_period"] = get_last_synced_period()
    except Exception:
        result["last_synced_period"] = {}
    return result
