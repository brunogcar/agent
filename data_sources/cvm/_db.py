"""data_sources/cvm/_db.py -- Shared database utilities for ALL cvm sub-domains.

Provides:
  - Path resolution (cvm data dir, dfp.db path, itr.db path, bridge.db path)
  - CNPJ normalization (strip formatting → 14-digit string)
  - Connection helpers (read-only + read-write)
  - Schema creation (empresas + contas + sync_state tables)

Used by: dfp/, itr/, and future sub-domains (fre, ipe).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from core.config import cfg


# ── CNPJ normalization ────────────────────────────────────────────────────────

def cnpj_digits(raw: str) -> str:
    """Normalize CNPJ to 14-digit string.

    "33.000.167/0001-01" → "33000167000101"
    Returns "" if result is not exactly 14 digits.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else ""


# ── Escala (scale) parsing ───────────────────────────────────────────────────

# CVM CSVs store ESCALA_MOEDA as a Portuguese word, not a number.
# This maps the known values to their numeric multipliers.
_ESCALA_MAP = {
    "MIL":      1_000,        # thousands
    "MILHAR":   1_000,        # thousands (variant)
    "MILHOES":  1_000_000,    # millions
    "MILHAO":   1_000_000,    # million (singular variant)
    "UNIDADE":  1,            # units (no scaling)
    "UNIDADES": 1,            # units (plural variant)
    "":         1,            # empty = treat as units
}


def parse_escala(escala: str | None) -> float:
    """Parse CVM ESCALA_MOEDA string to a numeric multiplier.

    CVM CSVs store scale as Portuguese words: "MIL" (thousands),
    "MILHOES" (millions), "UNIDADE" (units). This converts them to numbers
    so valor * escala = actual BRL.

    Args:
        escala: Raw ESCALA_MOEDA string from CVM CSV (e.g., "MIL", "MILHOES").

    Returns:
        Numeric multiplier (1, 1000, or 1000000). Returns 1 if unknown/empty.

    Examples:
        parse_escala("MIL") → 1000.0
        parse_escala("MILHOES") → 1000000.0
        parse_escala("UNIDADE") → 1.0
        parse_escala("") → 1.0
        parse_escala(None) → 1.0
    """
    if not escala:
        return 1.0
    key = str(escala).strip().upper()
    # Direct lookup
    if key in _ESCALA_MAP:
        return float(_ESCALA_MAP[key])
    # Try parsing as a number directly (some sources may store numeric)
    try:
        return float(key)
    except ValueError:
        return 1.0  # unknown escala = treat as units (safe default)


# ── Path resolution ───────────────────────────────────────────────────────────

def cvm_data_dir() -> Path:
    """Return the CVM data directory.

    Uses cfg.memory_root / "cvm" (co-located with ChromaDB + other data).
    Falls back to walking up from cwd to find a directory with "cvm" in it.
    """
    memory_root = getattr(cfg, "memory_root", None)
    if memory_root:
        d = Path(memory_root) / "cvm"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # Fallback: walk up from cwd
    p = Path.cwd()
    for _ in range(5):
        candidate = p / "memory_db" / "cvm"
        if candidate.exists():
            return candidate
        p = p.parent

    # Last resort: create in cwd
    d = Path.cwd() / "memory_db" / "cvm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def dfp_db_path() -> Path:
    """Return the path to the DFP database file."""
    return cvm_data_dir() / "dfp.db"


def itr_db_path() -> Path:
    """Return the path to the ITR database file."""
    return cvm_data_dir() / "itr.db"


def fre_db_path() -> Path:
    """Return the path to the FRE database file."""
    return cvm_data_dir() / "fre.db"


def ipe_db_path() -> Path:
    """Return the path to the IPE database file."""
    return cvm_data_dir() / "ipe.db"


def cad_db_path() -> Path:
    """Return the path to the CAD (company register) database file."""
    return cvm_data_dir() / "cad.db"


def bridge_db_path() -> Path:
    """Return the path to the B3-CVM bridge database (ticker → CNPJ mapping)."""
    return cvm_data_dir() / "bridge.db"


def connect_bridge(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the B3-CVM bridge database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).

    The schema (ticker_map + sync_log) is created by the bridge sub-domain's
    catalog.ensure_schema() during sync. This helper just opens the connection.
    """
    path = bridge_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(
                f"Bridge database not found at {path}. "
                f"Run data_source(domain='cvm', sub_domain='bridge', mode='sync') first."
            )
        conn = sqlite3.connect(str(path))
    else:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro" if read_only else str(path),
            uri=read_only,
        )
    conn.row_factory = sqlite3.Row
    return conn


# ── Connection helpers ────────────────────────────────────────────────────────

def connect_dfp(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the DFP database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = dfp_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"DFP database not found at {path}. Run sync first.")
        # Create the DB + schema for write mode
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_itr(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the ITR database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = itr_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"ITR database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_fre(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the FRE database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = fre_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"FRE database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn  # schema created by sync_engine

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_ipe(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the IPE database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = ipe_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"IPE database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn  # schema created by sync_engine

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_cad(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the CAD (company register) database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = cad_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"CAD database not found at {path}. Run sync first.")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn  # schema created by sync_engine

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the empresas + contas + sync_state tables if they don't exist.

    This schema is shared between DFP and ITR databases. Each DB has its own
    copy of empresas (slight redundancy, but keeps each DB self-contained).

    Schema design (mirrors rapinav2 with fixes):
      - empresas.ano = fiscal year (from DT_FIM_EXERC[:4]), NOT filing year
      - contas.data_ini_exerc = "" for BPA/BPP snapshots (needed to distinguish)
      - contas.meses = computed from DT_INI/DT_FIM (3, 6, 9, 12, 15)
      - contas.ordem_exerc = "ÚLTIMO"/"PENÚLTIMO" (for dedup)
      - contas.versao = filing version (highest kept)
      - PK includes data_ini_exerc (allows flow + snapshot with same data_fim_exerc)
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS empresas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj    TEXT NOT NULL,
            nome    TEXT NOT NULL,
            ano     INTEGER NOT NULL,
            cd_cvm  TEXT,
            UNIQUE (cnpj, ano)
        );

        CREATE TABLE IF NOT EXISTS contas (
            id_empresa     INTEGER NOT NULL,
            codigo         TEXT NOT NULL,
            descricao      TEXT NOT NULL,
            grupo          TEXT NOT NULL,
            consolidado    INTEGER NOT NULL,
            data_ini_exerc TEXT,
            data_fim_exerc TEXT NOT NULL,
            meses          INTEGER NOT NULL,
            ordem_exerc    TEXT,
            versao         INTEGER DEFAULT 1,
            st_conta_fixa  TEXT,
            valor          REAL NOT NULL,
            escala         TEXT,
            moeda          TEXT,
            FOREIGN KEY (id_empresa) REFERENCES empresas(id),
            PRIMARY KEY (id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc)
        );

        CREATE INDEX IF NOT EXISTS idx_contas_empresa ON contas(id_empresa);
        CREATE INDEX IF NOT EXISTS idx_contas_codigo ON contas(codigo);
        CREATE INDEX IF NOT EXISTS idx_contas_meses ON contas(meses);
        CREATE INDEX IF NOT EXISTS idx_contas_grupo ON contas(grupo);

        CREATE TABLE IF NOT EXISTS sync_state (
            form       TEXT,
            year       INTEGER,
            synced_at  TEXT,
            row_count  INTEGER DEFAULT 0,
            file_size  INTEGER DEFAULT 0,
            PRIMARY KEY (form, year)
        );
    """)
    conn.commit()
