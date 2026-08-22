"""skills/_freshness.py -- Top-level (cross-domain) data freshness helper.

Complements ``skills/cvm/_freshness.py`` (which is CVM/B3-only) by exposing
last-sync timestamps for DDM data sources. This module is the canonical
entry point for any consumer that wants a single dict covering DDM sources
without importing per-subdomain helpers.

Functions:
  - get_freshness()        -> {"ddm": str, "ddm-juros": str,
                               "ddm-poupanca": str, "ddm-acoes": str,
                               "ddm-focus": str}
    Each value is the ISO timestamp of the most recent ``sync_state`` row
    in the corresponding DB, or ``""`` if not synced yet.

The DDM family currently has 5 sub-domains:
  - ddm          (inflation: IGP-M, IPCA, INPC)               -> inflation.db
  - ddm-juros    (Selic, Meta Selic, CDI)                     -> juros.db
  - ddm-poupanca (Poupanca - savings account yield)           -> poupanca.db
  - ddm-acoes    (B3 listed stocks - PETR4, VALE3...)         -> acoes.db
  - ddm-focus    (Boletim Focus - market expectations survey) -> focus.db

All 5 DBs live in the shared ``memory_db/ddm/`` folder. The sync guard
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
    """Get last-sync timestamps for all DDM databases.

    Returns:
        ``{"ddm": ..., "ddm-juros": ..., "ddm-poupanca": ..., "ddm-acoes": ...}``
        Missing / unsynced DBs return ``""``.

    The keys match the ``sync_map`` keys in ``skills/_base._trigger_sync``
    so consumers can do ``fresh = get_freshness(); ensure_fresh([k for
    k, v in fresh.items() if not v])``.
    """
    result: dict[str, str] = {}

    # DDM Inflation (sync_map key = "ddm").
    try:
        from data_sources.ddm.inflation.catalog import db_path as ddm_inflation_path
        result["ddm"] = _check_db_freshness(ddm_inflation_path())
    except Exception:
        result["ddm"] = ""

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

    return result


def add_freshness(result: dict) -> dict:
    """Add data_freshness to a skill result dict (in-place + return).

    Usage at the end of a skill function:
        from skills._freshness import add_freshness
        return add_freshness(my_result)
    """
    try:
        result["data_freshness"] = get_freshness()
    except Exception:
        result["data_freshness"] = {}
    return result
