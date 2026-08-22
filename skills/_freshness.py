"""skills/_freshness.py — Data freshness helper for ALL skills.

Moved from skills/cvm/_freshness.py to the parent skills/ level so it can
track ALL data sources (CVM, B3, BCB, DDM) — not just CVM/B3.

Checks the sync_state table in each database and returns the last sync
timestamp. Used by skills/_base.py ensure_fresh() to determine if a
data source needs re-syncing (>24h old = stale).

Functions:
  - _check_db_freshness(db_path, table) — generic sync_state reader
  - get_freshness() — returns {source_name: iso_timestamp} for ALL sources
  - get_last_synced_period() — returns {cvm_source: last_data_period}
  - add_freshness(result) — adds data_freshness + last_synced_period to a dict
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
    """Get last-sync timestamps for ALL data source databases.

    Returns: {"dfp": "2026-07-24T...", "sgs": "...", "ddm-inflation": "...", ...}
    Missing/unsynced DBs return "".
    """
    result: dict[str, str] = {}

    # ── CVM databases ──────────────────────────────────────────────────
    try:
        from data_sources.cvm._db import (
            dfp_db_path, itr_db_path, fre_db_path, ipe_db_path,
            cad_db_path, vlmo_db_path, cgvn_db_path, fca_db_path,
        )
        from data_sources.cvm._db import bridge_db_path as bridge_path

        for name, path_fn in [
            ("dfp", dfp_db_path), ("itr", itr_db_path),
            ("fre", fre_db_path), ("ipe", ipe_db_path),
            ("cad", cad_db_path), ("vlmo", vlmo_db_path),
            ("cgvn", cgvn_db_path), ("fca", fca_db_path),
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
                result["bridge"] = str(row["synced_at"]) if row and row["synced_at"] else ""
                conn.close()
            else:
                result["bridge"] = ""
        except Exception:
            result["bridge"] = ""
    except Exception:
        pass

    # ── B3 databases ───────────────────────────────────────────────────
    try:
        from data_sources.b3.dividends.catalog import db_path as b3_div_path
        result["b3_dividends"] = _check_db_freshness(b3_div_path())
    except Exception:
        result["b3_dividends"] = ""

    try:
        from data_sources.b3.brapi.catalog import db_path as brapi_path
        result["brapi"] = _check_db_freshness(brapi_path())
    except Exception:
        result["brapi"] = ""

    try:
        from data_sources.b3.cotahist.catalog import db_path as cotahist_path
        cp = cotahist_path()
        if cp.exists():
            conn = sqlite3.connect(f"file:{cp}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT synced_at FROM sync_state ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                result["cotahist"] = str(row["synced_at"]) if row and row["synced_at"] else ""
            except Exception:
                result["cotahist"] = ""
            conn.close()
        else:
            result["cotahist"] = ""
    except Exception:
        result["cotahist"] = ""

    # ── BCB databases ──────────────────────────────────────────────────
    try:
        from data_sources.bcb.sgs.catalog import db_path as sgs_path
        result["sgs"] = _check_db_freshness(sgs_path())
    except Exception:
        result["sgs"] = ""

    try:
        from data_sources.bcb.focus.catalog import db_path as focus_path
        result["focus"] = _check_db_freshness(focus_path())
    except Exception:
        result["focus"] = ""

    # ── DDM databases ──────────────────────────────────────────────────
    try:
        from data_sources.ddm.inflation.catalog import db_path as ddm_inf_path
        result["ddm-inflation"] = _check_db_freshness(ddm_inf_path())
    except Exception:
        result["ddm-inflation"] = ""

    try:
        from data_sources.ddm.juros.catalog import db_path as ddm_jur_path
        result["ddm-juros"] = _check_db_freshness(ddm_jur_path())
    except Exception:
        result["ddm-juros"] = ""

    try:
        from data_sources.ddm.poupanca.catalog import db_path as ddm_pou_path
        result["ddm-poupanca"] = _check_db_freshness(ddm_pou_path())
    except Exception:
        result["ddm-poupanca"] = ""

    return result


def get_last_synced_period() -> dict[str, str]:
    """Get the last data period available in each CVM database.

    Returns {"dfp": "2023-12-31", "itr": "2024-06-30", ...} for CVM sources
    that have a contas table. Other sources return "".
    """
    from data_sources.cvm._db import (
        dfp_db_path, itr_db_path, fre_db_path, ipe_db_path,
        cad_db_path, vlmo_db_path, cgvn_db_path, fca_db_path,
    )

    result: dict[str, str] = {}
    for name, path_fn in [
        ("dfp", dfp_db_path), ("itr", itr_db_path),
        ("fre", fre_db_path), ("ipe", ipe_db_path),
        ("cad", cad_db_path), ("vlmo", vlmo_db_path),
        ("cgvn", cgvn_db_path), ("fca", fca_db_path),
    ]:
        try:
            p = path_fn()
            if not p.exists():
                result[name] = ""
                continue
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT MAX(data_fim_exerc) as max_date FROM contas"
                ).fetchone()
                result[name] = str(row["max_date"]) if row and row["max_date"] else ""
            except sqlite3.OperationalError:
                result[name] = ""
            conn.close()
        except Exception:
            result[name] = ""
    return result


def add_freshness(result: dict) -> dict:
    """Add data_freshness + last_synced_period to a skill result dict."""
    try:
        result["data_freshness"] = get_freshness()
    except Exception:
        result["data_freshness"] = {}
    try:
        result["last_synced_period"] = get_last_synced_period()
    except Exception:
        result["last_synced_period"] = {}
    return result
