"""
skills/cvm_register/cvm_register_api.py -- CVM company register (cad_cia_aberta.csv).

WHAT THIS IS
------------
The CVM maintains a public registry of all companies registered with them
(~3,500 companies, 1.5MB CSV). Updated weekly. Contains:
  - CNPJ, legal name, commercial name
  - CD_CVM: CVM's internal company code (links DFP/ITR/FRE filings)
  - Registration dates, cancellation status
  - Sector of activity, market type, registration category
  - Ownership control type (PRIVADO, ESTATAL, etc.)
  - Issuer situation (ATIVO, CANCELADA, EM RECUPERACAO JUDICIAL, etc.)
  - Address, contact, IR officer, auditor

SOURCE
------
https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
Updated: weekly by CVM
Encoding: ISO-8859-1 (Latin-1), separator: semicolon

STORAGE
-------
memory_db/cvm/register.db (SQLite, ~5MB)
State: memory_db/cvm/.register_state.json

LINKING TO OTHER SKILLS
-----------------------
CD_CVM  -> links to ITR/DFP filings (used internally by dfp_itr_sync to build contas)
CNPJ_CIA -> links to dfp_itr.db empresas.cnpj (join for financial data)
CNPJ_CIA -> links to isin.cnpj (after normalize) for B3 instruments
DENOM_COMERC / DENOM_SOCIAL -> human-readable lookup

DECISION: store all 46 columns even though many are contact details.
The skill filters to useful columns by default but exposes all for completeness.
Contact/address fields are useful for IR email, registered office, etc.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from core.config import cfg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_URL    = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
CSV_ENCODING = "ISO-8859-1"
CSV_SEP      = ";"

REGISTER_DB    = cfg.memory_root / "cvm" / "register.db"
STATE_FILE     = cfg.memory_root / "cvm" / ".register_state.json"
TABLE          = "cia_aberta"

DOWNLOAD_TIMEOUT = 60

# Columns to include in search/lookup results by default (skip contact noise)
DEFAULT_COLS = [
    "CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "CD_CVM",
    "SIT", "DT_INI_SIT", "SIT_EMISSOR", "DT_INI_SIT_EMISSOR",
    "DT_REG", "DT_CONST", "DT_CANCEL", "MOTIVO_CANCEL",
    "SETOR_ATIV", "TP_MERC", "CATEG_REG",
    "CONTROLE_ACIONARIO", "UF", "MUN",
    "EMAIL", "AUDITOR", "CNPJ_AUDITOR",
    "RESP", "EMAIL_RESP",
]

# All 46 columns from the CSV header (in order)
ALL_COLS = [
    "CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "DT_REG", "DT_CONST",
    "DT_CANCEL", "MOTIVO_CANCEL", "SIT", "DT_INI_SIT", "CD_CVM",
    "SETOR_ATIV", "TP_MERC", "CATEG_REG", "DT_INI_CATEG",
    "SIT_EMISSOR", "DT_INI_SIT_EMISSOR", "CONTROLE_ACIONARIO",
    "TP_ENDER", "LOGRADOURO", "COMPL", "BAIRRO", "MUN", "UF", "PAIS", "CEP",
    "DDD_TEL", "TEL", "DDD_FAX", "FAX", "EMAIL",
    "TP_RESP", "RESP", "DT_INI_RESP",
    "LOGRADOURO_RESP", "COMPL_RESP", "BAIRRO_RESP", "MUN_RESP",
    "UF_RESP", "PAIS_RESP", "CEP_RESP",
    "DDD_TEL_RESP", "TEL_RESP", "DDD_FAX_RESP", "FAX_RESP", "EMAIL_RESP",
    "CNPJ_AUDITOR", "AUDITOR",
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_dir() -> None:
    REGISTER_DB.parent.mkdir(parents=True, exist_ok=True)


def _connect(read_only: bool = False) -> sqlite3.Connection:
    if read_only and REGISTER_DB.exists():
        conn = sqlite3.connect(f"file:{REGISTER_DB}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(REGISTER_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _create_table(conn: sqlite3.Connection) -> None:
    """Create the cia_aberta table with indexes on the most-queried columns."""
    cols_sql = ",\n    ".join(f"{c} TEXT" for c in ALL_COLS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            {cols_sql}
        )
    """)
    # Indexes on the key lookup columns
    for col in ["CNPJ_CIA", "CD_CVM", "DENOM_COMERC", "DENOM_SOCIAL",
                "SIT", "SETOR_ATIV", "CONTROLE_ACIONARIO", "SIT_EMISSOR"]:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_{col} ON {TABLE}({col})"
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync(force: bool = False) -> dict:
    """
    Download cad_cia_aberta.csv from CVM and store to register.db.

    The file is ~1.5MB and updated weekly. Skip download if already synced
    today unless force=True.

    Returns sync result dict.
    """
    _ensure_dir()
    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    if not force and state.get("synced_at", "").startswith(today):
        return {
            "status":    "skipped",
            "reason":    "already synced today",
            "rows":      state.get("rows", 0),
            "synced_at": state.get("synced_at", ""),
        }

    t0 = time.time()
    try:
        resp = requests.get(CSV_URL, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        csv_text = resp.content.decode(CSV_ENCODING, errors="replace")
    except Exception as e:
        return {"status": "error", "error": f"Download failed: {e}"}

    # Parse CSV
    reader   = csv.DictReader(io.StringIO(csv_text), delimiter=CSV_SEP)
    rows     = list(reader)
    if not rows:
        return {"status": "error", "error": "CSV parsed to zero rows"}

    # Store to SQLite -- full replace each sync (file is a complete snapshot)
    conn = _connect()
    try:
        _create_table(conn)
        conn.execute(f"DELETE FROM {TABLE}")

        placeholders = ", ".join("?" * len(ALL_COLS))
        insert_sql   = f"INSERT INTO {TABLE} VALUES ({placeholders})"

        batch = []
        for row in rows:
            # Normalize: strip whitespace, use empty string for missing cols
            vals = tuple(str(row.get(c, "") or "").strip() for c in ALL_COLS)
            batch.append(vals)

        conn.executemany(insert_sql, batch)
        conn.commit()
    finally:
        conn.close()

    elapsed = round(time.time() - t0, 1)
    synced_at = datetime.utcnow().isoformat()

    state = {
        "rows":      len(rows),
        "synced_at": synced_at,
        "size_kb":   round(len(csv_text) / 1024, 1),
        "url":       CSV_URL,
    }
    _save_state(state)

    return {
        "status":    "synced",
        "rows":      len(rows),
        "size_kb":   state["size_kb"],
        "elapsed_s": elapsed,
        "synced_at": synced_at,
    }


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _normalize_cnpj(cnpj: str) -> str:
    """Strip formatting to numeric only: '33.000.167/0001-01' -> '33000167000101'"""
    return "".join(c for c in cnpj if c.isdigit())


def _rows_to_dicts(rows: list, cols: list[str]) -> list[dict]:
    """Convert sqlite3.Row list to plain dicts with selected columns."""
    result = []
    for row in rows:
        d = {}
        for col in cols:
            try:
                d[col] = row[col]
            except (IndexError, KeyError):
                d[col] = ""
        result.append(d)
    return result


def _build_where(
    cnpj:         str = "",
    cd_cvm:       str = "",
    name:         str = "",
    setor:        str = "",
    sit:          str = "",
    sit_emissor:  str = "",
    controle:     str = "",
    uf:           str = "",
    active_only:  bool = True,
) -> tuple[str, list]:
    """Build SQL WHERE clause from filter params. Returns (where_sql, params)."""
    parts:  list[str] = []
    params: list[Any] = []

    if cnpj:
        # Accept formatted or numeric CNPJ
        cnpj_n = _normalize_cnpj(cnpj)
        if cnpj_n:
            # Strip formatting from DB column too for comparison
            parts.append(
                "REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') LIKE ?"
            )
            params.append(f"%{cnpj_n}%")

    if cd_cvm:
        parts.append("CD_CVM = ?")
        params.append(str(cd_cvm).strip())

    if name:
        # Search both DENOM_SOCIAL (legal) and DENOM_COMERC (commercial)
        parts.append(
            "(UPPER(DENOM_SOCIAL) LIKE ? OR UPPER(DENOM_COMERC) LIKE ?)"
        )
        pct = f"%{name.upper()}%"
        params.extend([pct, pct])

    if setor:
        parts.append("UPPER(SETOR_ATIV) LIKE ?")
        params.append(f"%{setor.upper()}%")

    if sit:
        parts.append("UPPER(SIT) = ?")
        params.append(sit.upper())

    if sit_emissor:
        parts.append("UPPER(SIT_EMISSOR) LIKE ?")
        params.append(f"%{sit_emissor.upper()}%")

    if controle:
        parts.append("UPPER(CONTROLE_ACIONARIO) LIKE ?")
        params.append(f"%{controle.upper()}%")

    if uf:
        parts.append("UPPER(UF) = ?")
        params.append(uf.upper())

    # Default: only active companies (SIT = 'ATIVO')
    # DECISION: active_only=True by default because most queries are for
    # currently listed companies. Pass active_only=False to include cancelled.
    if active_only and not sit:
        parts.append("SIT = 'ATIVO'")

    where = f"WHERE {' AND '.join(parts)}" if parts else ""
    return where, params


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def lookup(
    cnpj:        str  = "",
    cd_cvm:      str  = "",
    name:        str  = "",
    full:        bool = False,
) -> dict:
    """
    Look up a single company by CNPJ, CD_CVM, or name.
    Returns the best match (exact first, then partial).

    cnpj:   company CNPJ, formatted or numeric
    cd_cvm: CVM internal code (numeric string, e.g. "9512")
    name:   company name or fragment (searches both legal and commercial name)
    full:   if True, return all 46 columns; default returns DEFAULT_COLS only

    This is the primary entry point for linking to other skills:
      result["CD_CVM"]   -> use with DFP/ITR filing queries
      result["CNPJ_CIA"] -> use with dfp_itr.db (cvm skill) and b3_api (isin join)
    """
    if not REGISTER_DB.exists():
        return {
            "status": "error",
            "error":  "register.db not found. Run: skill(domain='cvm_register', mode='sync')",
        }

    conn = _connect(read_only=True)
    try:
        cols = ALL_COLS if full else DEFAULT_COLS
        select = ", ".join(cols)

        # Try exact matches first, then partial
        queries = []
        params_list = []

        if cnpj:
            cnpj_n = _normalize_cnpj(cnpj)
            queries.append(
                f"SELECT {select} FROM {TABLE} WHERE "
                f"REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') = ? LIMIT 1"
            )
            params_list.append([cnpj_n])

        if cd_cvm:
            queries.append(f"SELECT {select} FROM {TABLE} WHERE CD_CVM = ? LIMIT 1")
            params_list.append([str(cd_cvm).strip()])

        if name:
            # Exact commercial name first, then partial
            queries.append(
                f"SELECT {select} FROM {TABLE} WHERE UPPER(DENOM_COMERC) = ? LIMIT 1"
            )
            params_list.append([name.upper()])
            queries.append(
                f"SELECT {select} FROM {TABLE} WHERE "
                f"(UPPER(DENOM_SOCIAL) LIKE ? OR UPPER(DENOM_COMERC) LIKE ?) LIMIT 5"
            )
            params_list.append([f"%{name.upper()}%", f"%{name.upper()}%"])

        for sql, params in zip(queries, params_list):
            rows = conn.execute(sql, params).fetchall()
            if rows:
                if len(rows) == 1:
                    return {
                        "status":  "ok",
                        "company": dict(rows[0]),
                    }
                else:
                    # Multiple matches -- return all for disambiguation
                    return {
                        "status":   "multiple",
                        "count":    len(rows),
                        "matches":  [dict(r) for r in rows],
                        "hint":     "Use CNPJ or CD_CVM for exact lookup",
                    }

        return {
            "status": "not_found",
            "error":  f"No company found for query: cnpj={cnpj!r} cd_cvm={cd_cvm!r} name={name!r}",
        }
    finally:
        conn.close()


def search(
    name:         str  = "",
    setor:        str  = "",
    sit:          str  = "",
    sit_emissor:  str  = "",
    controle:     str  = "",
    uf:           str  = "",
    active_only:  bool = True,
    limit:        int  = 20,
) -> dict:
    """
    Search companies with multiple filters. Returns a list.

    name:        company name fragment (searches legal and commercial name)
    setor:       sector fragment (e.g. "Energia", "Bancos", "Petróleo")
    sit:         exact registration status ("ATIVO", "CANCELADA", etc.)
    sit_emissor: issuer situation fragment ("RECUPERACAO", "PRE-OPERACIONAL", etc.)
    controle:    ownership control ("PRIVADO", "ESTATAL", "ESTRANGEIRO")
    uf:          state code ("SP", "RJ", "MG", etc.)
    active_only: filter to SIT='ATIVO' only (default True)
    limit:       max results (default 20)

    Examples:
      search(setor="Energia Elétrica")               # all active energy companies
      search(setor="Petróleo", uf="RJ")              # oil companies in Rio
      search(controle="ESTATAL")                     # state-owned companies
      search(sit_emissor="RECUPERACAO")              # companies in restructuring
      search(active_only=False, sit="CANCELADA")     # cancelled registrations
    """
    if not REGISTER_DB.exists():
        return {
            "status": "error",
            "error":  "register.db not found. Run: skill(domain='cvm_register', mode='sync')",
        }

    conn = _connect(read_only=True)
    try:
        where, params = _build_where(
            name=name, setor=setor, sit=sit, sit_emissor=sit_emissor,
            controle=controle, uf=uf, active_only=active_only,
        )
        params.append(limit)

        # Count total matches (for pagination awareness)
        count = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE} {where}", params[:-1]
        ).fetchone()[0]

        cols   = ", ".join(DEFAULT_COLS)
        rows   = conn.execute(
            f"SELECT {cols} FROM {TABLE} {where} "
            f"ORDER BY DENOM_COMERC LIMIT ?",
            params,
        ).fetchall()

        return {
            "status":       "ok",
            "total_matches": count,
            "returned":     len(rows),
            "limit":        limit,
            "companies":    _rows_to_dicts(rows, DEFAULT_COLS),
        }
    finally:
        conn.close()


def sectors() -> dict:
    """
    List all distinct sectors (SETOR_ATIV) with company counts.
    Useful for understanding the sector classification used by CVM.
    """
    if not REGISTER_DB.exists():
        return {"status": "error", "error": "register.db not found. Run sync first."}

    conn = _connect(read_only=True)
    try:
        rows = conn.execute(
            f"SELECT SETOR_ATIV, COUNT(*) as count FROM {TABLE} "
            f"WHERE SIT='ATIVO' AND SETOR_ATIV != '' "
            f"GROUP BY SETOR_ATIV ORDER BY count DESC"
        ).fetchall()
        return {
            "status":  "ok",
            "sectors": [{"setor": r["SETOR_ATIV"], "count": r["count"]} for r in rows],
            "total":   len(rows),
        }
    finally:
        conn.close()


def db_status() -> dict:
    """Show register.db sync status and basic stats."""
    state = _load_state()
    exists = REGISTER_DB.exists()
    size_kb = round(REGISTER_DB.stat().st_size / 1024, 1) if exists else 0

    result = {
        "status":    "ok" if exists else "not_synced",
        "db_path":   str(REGISTER_DB),
        "size_kb":   size_kb,
        "rows":      state.get("rows", 0),
        "synced_at": state.get("synced_at", ""),
        "source":    CSV_URL,
    }

    if exists:
        try:
            conn = _connect(read_only=True)
            total  = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
            active = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE SIT='ATIVO'").fetchone()[0]
            conn.close()
            result["total_companies"] = total
            result["active_companies"] = active
        except Exception:
            pass

    return result
