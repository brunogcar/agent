"""skills/_freshness.py -- Top-level (cross-domain) data freshness helper.

Complements ``skills/cvm/_freshness.py`` (which is CVM/B3-only) by exposing
last-sync timestamps for DDM data sources. This module is the canonical
entry point for any consumer that wants a single dict covering DDM sources
without importing per-subdomain helpers.

Functions:
  - get_freshness()        -> {"ddm": str, "ddm-juros": str,
                               "ddm-poupanca": str, "ddm-acoes": str,
                               "ddm-focus": str, "ddm-fluxo": str}
    Each value is the ISO timestamp of the most recent ``sync_state`` row
    in the corresponding DB, or ``""`` if not synced yet.

The DDM family currently has 6 sub-domains:
  - ddm          (inflation: IGP-M, IPCA, INPC)               -> inflation.db
  - ddm-juros    (Selic, Meta Selic, CDI)                     -> juros.db
  - ddm-poupanca (Poupanca - savings account yield)           -> poupanca.db
  - ddm-acoes    (B3 listed stocks - PETR4, VALE3...)         -> acoes.db
  - ddm-focus    (Boletim Focus - market expectations survey) -> focus.db
  - ddm-fluxo    (B3 investment flow by investor type)        -> fluxo.db

All 6 DBs live in the shared ``memory_db/ddm/`` folder. The sync guard
(``skills/_base._trigger_sync.sync_map``) has a separate entry per
sub-domain so the dashboard can refresh only what's stale.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _check_db_freshness(db_path: Path, table: str = "sync_state") -> str:
    """Check the last sync timestamp in a database's sync_state table.

    Mirrors skills/cvm/_freshness._check_db_freshness: returns ISO
    timestamp string of the most recent row, or ``""`` if the DB /
    table / column is missing.

    Args:
        db_path: Path to the SQLite database file.
        table:   Table name holding the sync metadata. Default "sync_state".
    """
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Try common column names for the timestamp (mirrors cvm heuristic).
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

    The keys match the ``sync_map`` keys in ``skills/_base._trigger_sync``
    so consumers can do ``fresh = get_freshness(); ensure_fresh([k for
    k, v in fresh.items() if not v])``.

    [v2 fix B1] Restored CVM + B3 + BCB sections that were lost during
    the 4ebdabf "move" from skills/cvm/_freshness.py. The DDM-only version
    at main caused _source_last_sync() to return "" for every non-DDM
    source, making every CVM/B3/BCB dashboard force-sync on every call.
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

    # DDM Inflation (sync_map key = "ddm-inflation" — renamed from "ddm"
    # in v2 fix B3 to match the skill's REQUIRED_SOURCES).
    try:
        from data_sources.ddm.inflation.catalog import db_path as ddm_inflation_path
        result["ddm-inflation"] = _check_db_freshness(ddm_inflation_path())
    except Exception:
        result["ddm-inflation"] = ""

    # DDM Juros (sync_map key = "ddm-juros").
    try:
        from data_sources.ddm.juros.catalog import db_path as ddm_juros_path
        result["ddm-juros"] = _check_db_freshness(ddm_juros_path())
    except Exception:
        result["ddm-juros"] = ""

    # DDM Poupanca (sync_map key = "ddm-poupanca").
    try:
        from data_sources.ddm.poupanca.catalog import db_path as ddm_poupanca_path
        result["ddm-poupanca"] = _check_db_freshness(ddm_poupanca_path())
    except Exception:
        result["ddm-poupanca"] = ""

    # DDM Acoes (sync_map key = "ddm-acoes").
    try:
        from data_sources.ddm.acoes.catalog import db_path as ddm_acoes_path
        result["ddm-acoes"] = _check_db_freshness(ddm_acoes_path())
    except Exception:
        result["ddm-acoes"] = ""

    # DDM Focus (sync_map key = "ddm-focus").
    try:
        from data_sources.ddm.focus.catalog import db_path as ddm_focus_path
        result["ddm-focus"] = _check_db_freshness(ddm_focus_path())
    except Exception:
        result["ddm-focus"] = ""

    # DDM Fluxo (sync_map key = "ddm-fluxo").
    try:
        from data_sources.ddm.fluxo.catalog import db_path as ddm_fluxo_path
        result["ddm-fluxo"] = _check_db_freshness(ddm_fluxo_path())
    except Exception:
        result["ddm-fluxo"] = ""

    # DDM Dividends (sync_map key = "ddm-dividends").
    # [v2 fix B2] Added alongside the sync_map entry — was missing, causing
    # _source_last_sync("ddm-dividends") to return "" even when the DB
    # was freshly synced.
    try:
        from data_sources.ddm.dividends.catalog import db_path as ddm_div_path
        result["ddm-dividends"] = _check_db_freshness(ddm_div_path())
    except Exception:
        result["ddm-dividends"] = ""

    return result


def get_last_synced_period() -> dict[str, str]:
    """Get the last data period available in each CVM database.

    Returns {"dfp": "2023-12-31", "itr": "2024-06-30", ...} for CVM sources
    that have a contas table. Other sources return "".

    [v2 fix B1] Restored from the old skills/cvm/_freshness.py (deleted in
    commit 4ebdabf). The function was lost during the "move" — the DDM
    freshness was extracted to skills/_freshness.py but the CVM-specific
    get_last_synced_period was not carried over, causing 4 CVM freshness
    tests to fail.
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
    """Add data_freshness + last_synced_period to a skill result dict.

    Usage at the end of a skill function:
        from skills._freshness import add_freshness
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
