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
# [v1.2] parse_escala moved to core/br_validator.py for reuse across skills.
# Re-exported here for backward compatibility with existing callers.

from core.br_validator import parse_escala  # noqa: E402, F401


# ── Path resolution ───────────────────────────────────────────────────────────

def cvm_db_path() -> Path:
    """Return the CVM database directory (base path for all CVM .db files).

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
    return cvm_db_path() / "dfp.db"


def itr_db_path() -> Path:
    """Return the path to the ITR database file."""
    return cvm_db_path() / "itr.db"


def fre_db_path() -> Path:
    """Return the path to the FRE database file."""
    return cvm_db_path() / "fre.db"


def ipe_db_path() -> Path:
    """Return the path to the IPE database file."""
    return cvm_db_path() / "ipe.db"


def cad_db_path() -> Path:
    """Return the path to the CAD (company register) database file."""
    return cvm_db_path() / "cad.db"


def bridge_db_path() -> Path:
    """Return the path to the B3-CVM bridge database (ticker → CNPJ mapping)."""
    return cvm_db_path() / "bridge.db"


def fca_db_path() -> Path:
    """Return the path to the FCA (Formulário Cadastral) database file.

    [v1.3] FCA contains ticker → CNPJ mapping (fca_valor_mobiliario table),
    making it the primary bridge resolver (local query, no network needed).
    Also contains listing segment (Novo Mercado, Nível 1, etc.) + foreign listings.
    """
    return cvm_db_path() / "fca.db"


def connect_fca(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the FCA database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = fca_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"FCA database not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn




def vlmo_db_path() -> Path:
    """Return the path to the VLMO (insider trading) database file."""
    return cvm_db_path() / "vlmo.db"


def connect_vlmo(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the VLMO database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = vlmo_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"VLMO database not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def cgvn_db_path() -> Path:
    """Return the path to the CGVN (governance practices) database file."""
    return cvm_db_path() / "cgvn.db"


def connect_cgvn(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the CGVN database.

    Args:
        read_only: If True, opens in read-only mode (for queries).
                   If False, opens in read-write mode (for sync).
    """
    path = cgvn_db_path()
    if not path.exists():
        if read_only:
            raise FileNotFoundError(f"CGVN database not found at {path}. Run sync first.")
        path.parent.mkdir(parents=True, exist_ok=True)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
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


# ── Company fingerprint (for engine cache invalidation) ─────────────────────


def _get_company_fingerprint(cnpj: str) -> str | None:
    """Get a data fingerprint for a company across DFP + ITR databases.

    Returns MAX(versao)|MAX(data_fim_exerc)|SUM(versao)|COUNT(*) for that CNPJ.
    This is used by data_sources._cache to determine if cached engine
    results are still valid.

    The fingerprint changes when:
      - A new filing version is published (MAX(versao) increments)
      - A new period is added (MAX(data_fim_exerc) changes, COUNT(*) increments)
      - A restated filing replaces an old one (SUM(versao) changes even if
        MAX(versao) doesn't — this catches per-period restatements that the
        old MAX-only fingerprint missed)
      - A filing is withdrawn (COUNT(*) drops)

    Queries both DFP and ITR (taking the MAX/SUM/COUNT across both) so a new
    quarterly ITR filing invalidates the cache even if DFP hasn't changed.

    Args:
        cnpj: 14-digit CNPJ string (digits only).

    Returns:
        Fingerprint string like "3|2025-12-31|47|1250", or None if the
        company isn't found in either database.
    """
    if not cnpj:
        return None

    # Normalize to digits
    cnpj = "".join(c for c in cnpj if c.isdigit())
    if len(cnpj) != 14:
        return None

    max_versao = 0
    max_data_fim = ""
    sum_versao = 0
    count_rows = 0

    for connect_fn in (connect_dfp, connect_itr):
        try:
            conn = connect_fn(read_only=True)
            try:
                # Find empresa_ids for this CNPJ
                rows = conn.execute(
                    "SELECT id FROM empresas WHERE cnpj = ?",
                    (cnpj,),
                ).fetchall()
                if not rows:
                    continue
                emp_ids = [str(r[0]) for r in rows]
                emp_ph = ",".join("?" * len(emp_ids))

                # Get MAX(versao) + MAX(data_fim_exerc) + SUM(versao) + COUNT(*)
                # SUM(versao) catches per-period restatements that MAX(versao) misses
                # COUNT(*) catches row additions/deletions
                row = conn.execute(
                    f"""SELECT MAX(versao) as max_v, MAX(data_fim_exerc) as max_d,
                               SUM(versao) as sum_v, COUNT(*) as cnt
                        FROM contas
                        WHERE id_empresa IN ({emp_ph})
                          AND consolidado = 1""",
                    emp_ids,
                ).fetchone()
                if row and row[0] is not None:
                    max_versao = max(max_versao, int(row[0]))
                if row and row[1] is not None and row[1] > max_data_fim:
                    max_data_fim = row[1]
                if row and row[2] is not None:
                    sum_versao += int(row[2])
                if row and row[3] is not None:
                    count_rows += int(row[3])
            finally:
                conn.close()
        except (FileNotFoundError, Exception):
            continue

    if max_data_fim == "":
        return None  # company not found in either DB

    return f"{max_versao}|{max_data_fim}|{sum_versao}|{count_rows}"
