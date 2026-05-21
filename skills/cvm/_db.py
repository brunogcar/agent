"""
skills/cvm/_db.py
Deploy to: D:\mcp\agent\skills\cvm\_db.py

Shared database utilities for ALL cvm sub-domains.
Imported by: cvm_dividends, cvm_shareholders, cvm_api, cvm_register,
             and future cvm_dfp_itr, cvm_ipe, cvm_fre.

FUTURE: When cvm_dfp_itr replaces cvm_api, add dfp_itr_path() here.
When cvm_ipe/cvm_fre are added, add ipe_path() / fre_path() here.
Each sub-domain gets its own DB file, all resolved the same way.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path


# ── CNPJ normalization ────────────────────────────────────────────────────────

def cnpj_digits(raw: str) -> str:
    """
    Normalize CNPJ to 14-digit string.
    Strips dots, slashes, dashes ("33.000.167/0001-01" -> "33000167000101").
    Returns "" if result is not exactly 14 digits.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else ""


# Backward-compatible alias used in older cvm_* code
_cnpj = cnpj_digits


# ── CVM data directory ────────────────────────────────────────────────────────

def cvm_data_dir() -> Path:
    """
    Return memory_db/cvm/ directory. Creates it if missing.

    Resolution order:
      1. MEMORY_ROOT env var (set in .env)
      2. Walk up from this file looking for memory_db/cvm/

    DECISION: MEMORY_ROOT is canonical. Walk-up is for dev environments
    where .env hasn't been loaded yet.
    """
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        d = Path(memory_root) / "cvm"
        d.mkdir(parents=True, exist_ok=True)
        return d

    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "memory_db" / "cvm"
        if candidate.exists():
            return candidate
        here = here.parent

    raise FileNotFoundError(
        "Cannot locate memory_db/cvm/. "
        "Set MEMORY_ROOT in .env (e.g. MEMORY_ROOT=D:/mcp/agent/memory_db)."
    )


# ── Database path helpers ─────────────────────────────────────────────────────

def rapina_path() -> Path:
    """
    Path to rapina.db (current name for DFP/ITR database).

    FUTURE RENAME: becomes dfp_itr_path() when rapina.db -> dfp_itr.db.
    Update this function and all callers get the new path automatically.
    """
    p = cvm_data_dir() / "rapina.db"
    if not p.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {p}. "
            "Run cvm_api(mode='sync') or rapina2 sync to populate it."
        )
    return p


def bridge_path() -> Path:
    """Path to bridge.db. Created by b3_cvm(mode='sync'). May not exist yet."""
    return cvm_data_dir() / "bridge.db"


# ── Connection helpers ────────────────────────────────────────────────────────

def connect_rapina() -> sqlite3.Connection:
    """Open rapina.db read-only with Row factory."""
    path = rapina_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Bridge schema ─────────────────────────────────────────────────────────────

# Required columns for the current bridge schema.
# Used by connect_bridge() to detect outdated schemas and trigger migration.
_BRIDGE_REQUIRED_COLS = {
    "ticker", "isin", "b3_name", "sgmt", "catg", "spec_cd",
    "gov_level", "mkt_cap", "cnpj", "cd_cvm", "denom_social",
    "denom_comerc", "sit", "tp_merc", "setor_ativ", "rapina_ids", "synced_at",
}

_BRIDGE_DDL = """
    CREATE TABLE IF NOT EXISTS company_map (
        ticker       TEXT NOT NULL,
        isin         TEXT NOT NULL,
        b3_name      TEXT DEFAULT '',
        sgmt         TEXT DEFAULT '',
        catg         TEXT DEFAULT '',
        spec_cd      TEXT DEFAULT '',
        gov_level    TEXT DEFAULT '',
        mkt_cap      REAL DEFAULT 0,
        cnpj         TEXT DEFAULT '',
        cd_cvm       INTEGER DEFAULT 0,
        denom_social TEXT DEFAULT '',
        denom_comerc TEXT DEFAULT '',
        sit          TEXT DEFAULT '',
        tp_merc      TEXT DEFAULT '',
        setor_ativ   TEXT DEFAULT '',
        rapina_ids   TEXT DEFAULT '[]',
        synced_at    TEXT DEFAULT '',
        PRIMARY KEY (ticker, isin)
    );
    CREATE INDEX IF NOT EXISTS idx_bridge_cnpj   ON company_map(cnpj);
    CREATE INDEX IF NOT EXISTS idx_bridge_cd_cvm ON company_map(cd_cvm);
    CREATE INDEX IF NOT EXISTS idx_bridge_ticker ON company_map(ticker);
    CREATE INDEX IF NOT EXISTS idx_bridge_sgmt   ON company_map(sgmt);
    CREATE INDEX IF NOT EXISTS idx_bridge_catg   ON company_map(catg);

    CREATE TABLE IF NOT EXISTS sync_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        synced_at   TEXT NOT NULL,
        instruments INTEGER DEFAULT 0,
        isin_cnpj   INTEGER DEFAULT 0,
        cvm_rows    INTEGER DEFAULT 0,
        bridge_rows INTEGER DEFAULT 0,
        matched_cvm INTEGER DEFAULT 0,
        matched_rap INTEGER DEFAULT 0,
        duration_s  REAL DEFAULT 0,
        notes       TEXT DEFAULT ''
    );
"""


def connect_bridge(read_only: bool = True) -> sqlite3.Connection:
    """
    Open bridge.db. Creates schema on first write-mode open.
    Migrates (drops + recreates company_map) if schema is outdated.

    MIGRATION STRATEGY: Drop company_map and recreate if any required
    column is missing. sync_log is preserved -- it uses additive columns
    only and is not affected by company_map schema changes.
    This is safe because bridge.db is fully rebuildable via mode_sync().

    DECISION: read_only=True default -- most callers only read.
    Only mode_sync() opens with read_only=False.
    """
    path = bridge_path()

    if read_only and not path.exists():
        raise FileNotFoundError(
            "bridge.db not found. Run skill(domain='b3_cvm', mode='sync') first."
        )

    conn = sqlite3.connect(
        f"file:{path}?mode=ro" if read_only else str(path),
        uri=read_only,
    )
    conn.row_factory = sqlite3.Row

    if not read_only:
        # ── Schema migration ──────────────────────────────────────────────────
        # Check if company_map exists and has all required columns.
        # If not, drop it so _BRIDGE_DDL recreates it correctly.
        existing_cols = {
            row[1] for row in
            conn.execute("PRAGMA table_info(company_map)").fetchall()
        }
        if existing_cols and not _BRIDGE_REQUIRED_COLS.issubset(existing_cols):
            missing = _BRIDGE_REQUIRED_COLS - existing_cols
            print(
                f"[_db] bridge.db schema outdated (missing: {missing}). "
                "Dropping company_map + sync_log for rebuild.",
                file=sys.stderr,
            )
            conn.execute("DROP TABLE IF EXISTS company_map")
            conn.execute("DROP TABLE IF EXISTS sync_log")
            # Drop indexes explicitly (SQLite drops them with the table,
            # but being explicit avoids any edge case with partial states)
            for idx in ("idx_bridge_cnpj", "idx_bridge_cd_cvm",
                        "idx_bridge_ticker", "idx_bridge_sgmt", "idx_bridge_catg"):
                conn.execute(f"DROP INDEX IF EXISTS {idx}")
            conn.commit()

        conn.executescript(_BRIDGE_DDL)
        conn.commit()

    return conn


# ── rapina CNPJ index ─────────────────────────────────────────────────────────

def build_rapina_cnpj_index() -> dict[str, list[int]]:
    """
    Build {cnpj: [empresa_id, ...]} from rapina.db.

    One CNPJ maps to many empresa.ids (one per fiscal period).
    Petrobras has 40+ rows covering quarterly periods from 2016 to 2025.

    DECISION: Collect ALL ids sorted ascending ([0]=oldest, [-1]=newest).
    The consuming mode filters by dt_refer -- not by id value.
    Returns {} if rapina.db not found (bridge still works, rapina_ids=[]).
    """
    try:
        conn = connect_rapina()
    except FileNotFoundError as e:
        print(f"[_db] WARNING: {e}", file=sys.stderr)
        return {}

    try:
        rows = conn.execute(
            "SELECT id, cnpj FROM empresas "
            "WHERE cnpj IS NOT NULL AND cnpj != '' ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()

    index: dict[str, list[int]] = {}
    for row in rows:
        c = cnpj_digits(str(row["cnpj"]))
        if c:
            index.setdefault(c, []).append(row["id"])

    for c in index:
        index[c] = sorted(set(index[c]))

    total = sum(len(v) for v in index.values())
    print(f"[_db] rapina index: {len(index):,} CNPJs | {total:,} empresa rows",
          file=sys.stderr)
    return index
