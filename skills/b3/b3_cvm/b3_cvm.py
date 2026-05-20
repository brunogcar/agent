"""
skills/b3/b3_cvm/b3_cvm.py -- B3-CVM company identity bridge.

=== WHAT THIS FILE DOES ===
Builds and queries bridge.db, a local SQLite database that maps:

    TICKER (B3) <-> ISIN <-> CNPJ <-> CD_CVM (CVM) <-> rapina_ids

This solves the cross-skill identity problem: every other skill identifies
companies differently (ticker, CD_CVM, rapina empresa.id, name), and without
a bridge they cannot talk to each other.

=== DATA SOURCES (mode="sync") ===

1. B3 ISIN file (downloaded fresh each sync):
   URL flow:
     GET .../IsinCall/GetTextDownload/
       => {"geralPt": {"id": 102001, "dataGeracao": "..."}}
     base64(json.dumps(102001)) => "MTAyMDAx"
     GET .../IsinCall/GetFileDownload/MTAyMDAx
       => pipe-delimited TXT, ~50k rows, UTF-8 or latin-1
   Columns confirmed from rapinav2 README + B3 API exploration:
     Codigo ISIN | Codigo do Instrumento (ticker) | Descricao | Situacao |
     Tipo Mercado | CNPJ | ... (column count varies by file version)

2. CVM cad_cia_aberta.csv (downloaded fresh each sync):
   URL: https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
   Semicolon-delimited, UTF-8 with BOM or latin-1
   Key columns:
     CD_CVM | CNPJ_CIA | DENOM_SOCIAL | DENOM_COMERC | SIT | TP_MERC | SETOR_ATIV

3. rapina.db (already local, read-only):
   Table: empresas
     id | nome | cnpj (digits only) | ano | dt_refer
   Used to pre-compute rapina_ids per CNPJ for instant cross-skill queries.

=== CNPJ NORMALIZATION ===
CNPJ appears in three formats across sources:
  B3 ISIN file:  "33.000.167/0001-01"  (punctuated)
  CVM CSV:       "33.000.167/0001-01"  (punctuated)
  rapina.db:     "33000167000101"      (digits only)

DECISION: normalize everything to 14 digits (strip non-digits) as the
canonical join key. The _cnpj() helper does this throughout the module.

=== BRIDGE.DB SCHEMA ===
One row per (ticker, isin) combination.
Same company can have multiple tickers: PETR3, PETR4, PETR4F all share
the same CNPJ/CD_CVM/rapina_ids.

CREATE TABLE company_map (
    ticker       TEXT,       -- B3 code e.g. "PETR4"
    isin         TEXT,       -- e.g. "BRPETRACNPR6"
    b3_name      TEXT,       -- B3 instrument description
    b3_sit       TEXT,       -- B3 situation: "Ativo", "Inativo"...
    b3_type      TEXT,       -- instrument type from B3
    cnpj         TEXT,       -- 14 digits, the universal join key
    cd_cvm       INTEGER,    -- CVM integer code
    denom_social TEXT,       -- CVM official name (razao social)
    denom_comerc TEXT,       -- CVM commercial name (nome fantasia)
    sit          TEXT,       -- CVM situation: ATIVO/CANCELADO/SUSPENSO
    tp_merc      TEXT,       -- CVM market: BOVESPA/BALCAO/etc.
    setor_ativ   TEXT,       -- CVM economic sector
    rapina_ids   TEXT,       -- JSON array of rapina empresa.id ints
    synced_at    TEXT,       -- ISO timestamp of last sync
    PRIMARY KEY (ticker, isin)
)

=== DECISION: rapina_ids as JSON array in TEXT column ===
Alternatives considered:
  a) Separate junction table (company_map_rapina_ids)
     Rejected: overkill for this use case, complicates queries
  b) Comma-separated string
     Rejected: ambiguous with edge cases (empty, single)
  c) JSON array TEXT (chosen)
     json.loads() is one line, sqlite3 handles TEXT natively,
     and the agent can pass the list directly to rapina queries.
     Typical size: 4-40 ids per company (one per quarter for 10 years).

=== DECISION: separate bridge.db file (not rapina.db or agent.db) ===
Alternatives considered:
  a) Add table to rapina.db
     Rejected: rapina.db is a third-party data store (rapinav2), we
     should not pollute it with our own tables. It may be refreshed/replaced.
  b) Add table to agent.db (memory_db/agent.db)
     Rejected: agent.db is for task queue state. Different concern.
  c) Separate bridge.db (chosen)
     Clean separation of concerns. Easy to delete and rebuild.
     Location: memory_db/cvm/bridge.db (same dir as rapina.db)
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Path helpers ──────────────────────────────────────────────────────────────

def _cvm_dir() -> Path:
    """Return memory_db/cvm/ directory. Must already exist (rapina.db lives here)."""
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        d = Path(memory_root) / "cvm"
        d.mkdir(parents=True, exist_ok=True)
        return d
    # Fallback: walk up from this file looking for memory_db/cvm/
    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "memory_db" / "cvm"
        if candidate.exists():
            return candidate
        here = here.parent
    raise FileNotFoundError(
        "Cannot locate memory_db/cvm/. Set MEMORY_ROOT env var."
    )


def _bridge_path() -> Path:
    return _cvm_dir() / "bridge.db"


def _rapina_path() -> Path:
    p = _cvm_dir() / "rapina.db"
    if not p.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {p}. Run cvm_api(mode='sync') first."
        )
    return p


# ── CNPJ normalization ────────────────────────────────────────────────────────

def _cnpj(raw: str) -> str:
    """Strip any non-digit characters. Returns 14-digit string or empty."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else digits.zfill(14) if 0 < len(digits) <= 14 else digits


# ── Bridge DB connection ──────────────────────────────────────────────────────

def _bridge_conn(read_only: bool = False) -> sqlite3.Connection:
    """Open bridge.db. Creates it with schema if it doesn't exist yet."""
    path = _bridge_path()

    if read_only and not path.exists():
        raise FileNotFoundError(
            "bridge.db not found. Run skill(domain='b3_cvm', mode='sync') first."
        )

    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))

    conn.row_factory = sqlite3.Row

    # Create schema on first open (idempotent)
    if not read_only:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS company_map (
                ticker       TEXT NOT NULL,
                isin         TEXT NOT NULL,
                b3_name      TEXT DEFAULT '',
                b3_sit       TEXT DEFAULT '',
                b3_type      TEXT DEFAULT '',
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
            CREATE INDEX IF NOT EXISTS idx_bridge_cnpj    ON company_map(cnpj);
            CREATE INDEX IF NOT EXISTS idx_bridge_cd_cvm  ON company_map(cd_cvm);
            CREATE INDEX IF NOT EXISTS idx_bridge_ticker  ON company_map(ticker);
            CREATE INDEX IF NOT EXISTS idx_bridge_sit     ON company_map(sit);

            -- sync_log tracks each sync run for debugging
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at   TEXT NOT NULL,
                b3_rows     INTEGER DEFAULT 0,
                cvm_rows    INTEGER DEFAULT 0,
                bridge_rows INTEGER DEFAULT 0,
                matched     INTEGER DEFAULT 0,
                duration_s  REAL DEFAULT 0,
                notes       TEXT DEFAULT ''
            );
        """)
        conn.commit()

    return conn


# ── B3 ISIN file download ─────────────────────────────────────────────────────

def _fetch_b3_isin_file() -> list[dict]:
    """
    Download the B3 daily ISIN file and return parsed rows.

    Flow (as documented in rapinav2 README):
      1. GET GetTextDownload/ -> JSON with geralPt.id
      2. base64-encode the integer id
      3. GET GetFileDownload/{encoded_id} -> pipe-delimited TXT

    Returns list of dicts with keys:
      isin, ticker, name, situation, type, cnpj, market

    DECISION: We use the "geralPt" (Portuguese, general/complete) file.
    There are also "geralEn" (English), "mensalPt" (monthly), and
    "diariosPt" (daily delta) variants. We want the complete file because:
      - daily deltas miss deletions
      - monthly is outdated for new listings
      - Complete Portuguese file has the most complete CNPJ data

    DECISION: Try multiple encodings (latin-1, utf-8, cp1252).
    B3's file encoding has varied historically. Try latin-1 first since
    it's a superset of ASCII and handles accented Portuguese characters
    in the company names correctly without exceptions.
    """
    import httpx

    # Step 1: get file index
    index_url = (
        "https://sistemaswebb3-listados.b3.com.br"
        "/isinProxy/IsinCall/GetTextDownload/"
    )
    print("[b3_cvm] Fetching B3 ISIN file index...", file=sys.stderr)
    resp = httpx.get(index_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    index = resp.json()

    file_id = index["geralPt"]["id"]
    gen_date = index["geralPt"].get("dataGeracao", "")
    print(
        f"[b3_cvm] B3 ISIN geralPt id={file_id}, generated={gen_date}",
        file=sys.stderr,
    )

    # Step 2: base64-encode the integer (btoa(JSON.stringify(id)) in JS)
    encoded_id = base64.b64encode(json.dumps(file_id).encode()).decode()

    # Step 3: download the actual file
    file_url = (
        f"https://sistemaswebb3-listados.b3.com.br"
        f"/isinProxy/IsinCall/GetFileDownload/{encoded_id}"
    )
    print(f"[b3_cvm] Downloading B3 ISIN file ({encoded_id})...", file=sys.stderr)
    resp = httpx.get(
        file_url,
        timeout=60,
        follow_redirects=True,
        headers={"Referer": "https://sistemaswebb3-listados.b3.com.br/isinPage"},
    )
    resp.raise_for_status()

    raw_bytes = resp.content
    print(f"[b3_cvm] Downloaded {len(raw_bytes):,} bytes", file=sys.stderr)

    # Step 4: decode and parse
    # DECISION: Try latin-1 first, then utf-8 with error replace.
    # B3 files are historically latin-1 (ISO-8859-1). The file has Portuguese
    # company names with accented characters (ã, é, ç, etc.). latin-1 handles
    # these without any escape sequences. utf-8 may also work for newer files.
    content = None
    for encoding in ("latin-1", "utf-8", "cp1252"):
        try:
            content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode("latin-1", errors="replace")

    return _parse_b3_isin_content(content)


def _parse_b3_isin_content(content: str) -> list[dict]:
    """
    Parse the B3 ISIN pipe-delimited file content.

    The file format (confirmed from B3 ISIN page structure):
      Line 1: header with column names
      Lines 2-N: data rows
      Last line: may be a summary/footer -- skip if non-data

    Column order may vary between files. We parse the header to find
    column positions rather than hardcoding indices.

    Expected columns (Portuguese names, exact names may vary slightly):
      Código ISIN | Código do Instrumento | Descrição do Instrumento |
      Situação | Tipo Mercado | Prazo | CNPJ | Emissor | ...

    DECISION: Be tolerant of missing/extra columns. We only require
    ISIN and ticker (Código do Instrumento). CNPJ is critical for the
    bridge but some instruments (ETFs, BDRs) may not have a CNPJ.
    We include them in bridge.db but with cnpj=''.
    """
    lines = content.splitlines()
    if not lines:
        return []

    # Parse header -- B3 uses pipe separator
    header_line = lines[0]
    sep = "|"
    headers = [h.strip() for h in header_line.split(sep)]

    # Map normalized header names to column indices
    # DECISION: normalize by lowercasing and removing accents/spaces
    # so slight variations in header text don't break parsing.
    def _norm(s: str) -> str:
        s = s.lower().strip()
        # Remove common accented chars
        for a, b in [("ã", "a"), ("ç", "c"), ("é", "e"), ("ê", "e"),
                     ("ó", "o"), ("ô", "o"), ("ú", "u"), ("á", "a"),
                     ("í", "i"), (" ", "_")]:
            s = s.replace(a, b)
        return s

    norm_headers = [_norm(h) for h in headers]

    def _col(candidates: list[str]) -> int:
        """Find column index by trying multiple candidate names."""
        for c in candidates:
            nc = _norm(c)
            if nc in norm_headers:
                return norm_headers.index(nc)
        return -1

    idx_isin   = _col(["Código ISIN", "Codigo ISIN", "ISIN"])
    idx_ticker = _col(["Código do Instrumento", "Codigo do Instrumento", "Instrumento", "Ticker"])
    idx_name   = _col(["Descrição do Instrumento", "Descricao do Instrumento", "Descricao", "Nome"])
    idx_sit    = _col(["Situação", "Situacao", "Sit"])
    idx_type   = _col(["Tipo Mercado", "Tipo", "Mercado"])
    idx_cnpj   = _col(["CNPJ", "CNPJ Emissor", "CNPJ_EMISSOR"])

    if idx_isin == -1 or idx_ticker == -1:
        # FALLBACK: assume fixed positions 0=ISIN, 1=ticker
        # This handles files where the header uses unexpected names
        print(
            f"[b3_cvm] WARNING: Could not find ISIN/ticker columns in header: {headers[:6]}. "
            "Falling back to positional parsing (0=ISIN, 1=ticker).",
            file=sys.stderr,
        )
        idx_isin, idx_ticker = 0, 1
        if idx_name == -1:
            idx_name = 2

    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(sep)
        if len(parts) < 2:
            continue

        def _get(idx: int) -> str:
            if idx < 0 or idx >= len(parts):
                return ""
            return parts[idx].strip()

        isin   = _get(idx_isin)
        ticker = _get(idx_ticker)

        # Skip rows without a valid ISIN (summary rows, blank lines)
        if not isin or len(isin) < 10:
            continue
        # Skip rows without a ticker (pure bond ISINs without a trading code)
        if not ticker:
            continue

        raw_cnpj = _get(idx_cnpj)
        rows.append({
            "isin":   isin,
            "ticker": ticker.upper(),
            "name":   _get(idx_name),
            "sit":    _get(idx_sit),
            "type":   _get(idx_type),
            "cnpj":   _cnpj(raw_cnpj),
        })

    print(f"[b3_cvm] Parsed {len(rows):,} B3 ISIN rows", file=sys.stderr)
    return rows


# ── CVM cad_cia_aberta.csv download ──────────────────────────────────────────

def _fetch_cvm_register() -> list[dict]:
    """
    Download CVM cad_cia_aberta.csv and return parsed rows.

    URL: https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv

    This file is updated daily by CVM and contains registration data for all
    publicly listed companies. It's the authoritative source for:
      - CD_CVM (the integer code used in all CVM document URLs)
      - DENOM_SOCIAL (official razao social)
      - DENOM_COMERC (commercial/fantasy name)
      - CNPJ_CIA (CNPJ with punctuation)
      - SIT (ATIVO / CANCELADO / SUSPENSO / FASE PRE-OPERACIONAL)
      - TP_MERC (BOVESPA / BALCAO ORGANIZADO / BALCAO NAO ORGANIZADO)
      - SETOR_ATIV (economic sector)

    DECISION: Download the full CSV on every sync, not just deltas.
    At ~2MB for ~3k rows, the full file is fast to download and parse.
    Delta tracking would add complexity for minimal benefit.

    DECISION: Include CANCELADO/SUSPENSO companies in bridge.db.
    Reason: rapina.db may have historical data for cancelled companies
    (e.g. merged companies before cancellation). Including them lets
    the bridge answer "this CNPJ used to be listed as CD_CVM=X".
    The 'sit' column in bridge.db lets callers filter if needed.
    """
    import httpx

    cvm_url = (
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
    )
    print("[b3_cvm] Downloading CVM cad_cia_aberta.csv...", file=sys.stderr)
    resp = httpx.get(cvm_url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw_bytes = resp.content
    print(f"[b3_cvm] Downloaded {len(raw_bytes):,} bytes (CVM)", file=sys.stderr)

    # DECISION: Try UTF-8-BOM first (CVM sometimes adds BOM), then latin-1.
    # CVM files have historically been latin-1 but newer files may be UTF-8.
    content = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode("latin-1", errors="replace")

    return _parse_cvm_register(content)


def _parse_cvm_register(content: str) -> list[dict]:
    """
    Parse CVM cad_cia_aberta.csv (semicolon-delimited).

    The CVM file uses semicolons as delimiters (not commas) because Brazil
    uses commas as the decimal separator, so semicolons are the CSV standard
    for Portuguese-locale files. Headers are in the first line.

    Expected columns (from CVM data dictionary meta_cad_cia_aberta.txt):
      CD_CVM | DENOM_SOCIAL | DENOM_COMERC | CNPJ_CIA | SIT |
      DT_REG | DT_CANCEL | TP_MERC | SG_MERCADO | SETOR_ATIV |
      TP_ATIV | DT_INI_SIT | DT_INI_ATIV | ...

    DECISION: Parse by header column name (not position) so that CVM
    adding new columns in the future doesn't break the parser.
    """
    lines = content.splitlines()
    if not lines:
        return []

    headers = [h.strip() for h in lines[0].split(";")]
    col = {h: i for i, h in enumerate(headers)}

    def _get(parts: list[str], name: str, default: str = "") -> str:
        idx = col.get(name, -1)
        if idx < 0 or idx >= len(parts):
            return default
        return parts[idx].strip()

    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")

        cnpj_raw = _get(parts, "CNPJ_CIA")
        cd_cvm_raw = _get(parts, "CD_CVM", "0")

        try:
            cd_cvm = int(cd_cvm_raw)
        except ValueError:
            cd_cvm = 0

        rows.append({
            "cnpj":         _cnpj(cnpj_raw),
            "cd_cvm":       cd_cvm,
            "denom_social": _get(parts, "DENOM_SOCIAL"),
            "denom_comerc": _get(parts, "DENOM_COMERC"),
            "sit":          _get(parts, "SIT"),
            "tp_merc":      _get(parts, "TP_MERC"),
            "setor_ativ":   _get(parts, "SETOR_ATIV"),
        })

    print(f"[b3_cvm] Parsed {len(rows):,} CVM register rows", file=sys.stderr)
    return rows


# ── rapina.db CNPJ → empresa.id mapping ──────────────────────────────────────

def _build_rapina_index() -> dict[str, list[int]]:
    """
    Read rapina.db and return {cnpj: [id1, id2, ...]} mapping.

    One CNPJ can have many empresa.ids because rapina creates a new row
    per (company, fiscal_period). E.g. Petrobras has 40+ ids covering
    quarterly periods from 2016 to 2025.

    DECISION: We collect ALL ids (not just the most recent) because:
    - cvm_dividends queries DVA which is annual (any id for Dec-31 works)
    - cvm_api queries may need specific periods
    - The caller decides which ids to use based on dt_refer filtering
    Storing all ids is slightly larger but eliminates the need for the
    bridge to know about period semantics.

    DECISION: Sort ids ascending so [0] is the oldest and [-1] is newest.
    This gives callers a predictable ordering.
    """
    try:
        rapina = _rapina_path()
    except FileNotFoundError as e:
        print(f"[b3_cvm] WARNING: {e}. rapina_ids will be empty.", file=sys.stderr)
        return {}

    conn = sqlite3.connect(f"file:{rapina}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, cnpj FROM empresas WHERE cnpj IS NOT NULL AND cnpj != '' "
            "ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()

    index: dict[str, list[int]] = {}
    for row in rows:
        empresa_id, raw_cnpj = row
        cnpj = _cnpj(str(raw_cnpj))
        if cnpj:
            index.setdefault(cnpj, []).append(empresa_id)

    # Deduplicate (keep sorted)
    for cnpj in index:
        index[cnpj] = sorted(set(index[cnpj]))

    print(
        f"[b3_cvm] rapina index: {len(index):,} unique CNPJs, "
        f"{sum(len(v) for v in index.values()):,} total empresa rows",
        file=sys.stderr,
    )
    return index


# ── Mode: sync ────────────────────────────────────────────────────────────────

def mode_sync() -> dict:
    """
    Build or rebuild bridge.db from B3 ISIN + CVM register + rapina.db.

    Steps:
      1. Download B3 ISIN file -> parse -> {ticker: {isin, name, cnpj, ...}}
      2. Download CVM cad_cia_aberta.csv -> parse -> {cnpj: {cd_cvm, names, sit, ...}}
      3. Read rapina.db -> {cnpj: [empresa_ids]}
      4. Join on CNPJ -> write to bridge.db (UPSERT)
      5. Log result to sync_log

    Returns summary dict with counts and coverage statistics.
    """
    import time
    t0 = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: B3 ISIN
    try:
        b3_rows = _fetch_b3_isin_file()
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to download B3 ISIN file: {e}",
            "step": "b3_download",
        }

    # Step 2: CVM register
    try:
        cvm_rows = _fetch_cvm_register()
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to download CVM cad_cia_aberta.csv: {e}",
            "step": "cvm_download",
        }

    # Step 3: rapina index
    rapina_index = _build_rapina_index()

    # Step 4: Build CVM lookup dict {cnpj -> cvm_row}
    # DECISION: If multiple CVM rows have same CNPJ (shouldn't happen but
    # possible for companies that reregistered), prefer ATIVO status.
    cvm_by_cnpj: dict[str, dict] = {}
    for row in cvm_rows:
        cnpj = row["cnpj"]
        if not cnpj:
            continue
        existing = cvm_by_cnpj.get(cnpj)
        if existing is None:
            cvm_by_cnpj[cnpj] = row
        elif row.get("sit") == "ATIVO" and existing.get("sit") != "ATIVO":
            # Prefer ATIVO over CANCELADO/SUSPENSO
            cvm_by_cnpj[cnpj] = row

    # Step 5: Write to bridge.db
    conn = _bridge_conn(read_only=False)
    try:
        matched = 0
        inserted = 0
        no_cnpj = 0

        for b3 in b3_rows:
            cnpj = b3["cnpj"]

            if not cnpj:
                no_cnpj += 1
                # Still insert with empty CVM data -- bridge knows this ticker exists
                cvm = {}
            else:
                cvm = cvm_by_cnpj.get(cnpj, {})
                if cvm:
                    matched += 1

            rapina_ids = rapina_index.get(cnpj, [])

            conn.execute("""
                INSERT INTO company_map
                    (ticker, isin, b3_name, b3_sit, b3_type,
                     cnpj, cd_cvm, denom_social, denom_comerc,
                     sit, tp_merc, setor_ativ, rapina_ids, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, isin) DO UPDATE SET
                    b3_name      = excluded.b3_name,
                    b3_sit       = excluded.b3_sit,
                    b3_type      = excluded.b3_type,
                    cnpj         = excluded.cnpj,
                    cd_cvm       = excluded.cd_cvm,
                    denom_social = excluded.denom_social,
                    denom_comerc = excluded.denom_comerc,
                    sit          = excluded.sit,
                    tp_merc      = excluded.tp_merc,
                    setor_ativ   = excluded.setor_ativ,
                    rapina_ids   = excluded.rapina_ids,
                    synced_at    = excluded.synced_at
            """, (
                b3["ticker"],
                b3["isin"],
                b3["name"],
                b3["sit"],
                b3["type"],
                cnpj,
                cvm.get("cd_cvm", 0),
                cvm.get("denom_social", ""),
                cvm.get("denom_comerc", ""),
                cvm.get("sit", ""),
                cvm.get("tp_merc", ""),
                cvm.get("setor_ativ", ""),
                json.dumps(rapina_ids),
                now_iso,
            ))
            inserted += 1

        conn.commit()

        # Count total rows in bridge
        total = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0"
        ).fetchone()[0]
        with_rapina = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE rapina_ids != '[]'"
        ).fetchone()[0]

        duration = round(time.time() - t0, 1)

        # Log the sync run
        conn.execute("""
            INSERT INTO sync_log (synced_at, b3_rows, cvm_rows, bridge_rows, matched, duration_s, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso,
            len(b3_rows),
            len(cvm_rows),
            total,
            matched,
            duration,
            f"no_cnpj={no_cnpj}",
        ))
        conn.commit()

    finally:
        conn.close()

    coverage_pct = round(with_cvm / total * 100, 1) if total else 0
    rapina_pct   = round(with_rapina / total * 100, 1) if total else 0

    report = (
        f"=== B3-CVM Bridge Sync Complete ===\n"
        f"Duration        : {duration}s\n"
        f"B3 ISIN rows    : {len(b3_rows):,}\n"
        f"CVM register    : {len(cvm_rows):,}\n"
        f"Bridge total    : {total:,} tickers\n"
        f"B3 + CVM match  : {with_cvm:,} ({coverage_pct}% of tickers)\n"
        f"B3 + rapina     : {with_rapina:,} ({rapina_pct}% have financial data)\n"
        f"No CNPJ (bonds) : {no_cnpj:,}\n"
        f"Synced at       : {now_iso}\n"
    )
    print(f"[b3_cvm] {report}", file=sys.stderr)

    return {
        "status":       "success",
        "b3_rows":      len(b3_rows),
        "cvm_rows":     len(cvm_rows),
        "bridge_total": total,
        "with_cvm":     with_cvm,
        "with_rapina":  with_rapina,
        "no_cnpj":      no_cnpj,
        "coverage_pct": coverage_pct,
        "rapina_pct":   rapina_pct,
        "duration_s":   duration,
        "synced_at":    now_iso,
        "report":       report,
    }


# ── Mode: status ──────────────────────────────────────────────────────────────

def mode_status() -> dict:
    """
    Show bridge.db health: last sync, row counts, coverage stats.
    Does not hit the network.
    """
    path = _bridge_path()
    if not path.exists():
        return {
            "status":  "not_synced",
            "message": "bridge.db does not exist. Run skill(domain='b3_cvm', mode='sync').",
            "report":  "Bridge not yet synced.",
        }

    try:
        conn = _bridge_conn(read_only=True)
        total = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0"
        ).fetchone()[0]
        with_rapina = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE rapina_ids != '[]'"
        ).fetchone()[0]
        active_b3 = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE upper(b3_sit) LIKE '%ATIVO%'"
        ).fetchone()[0]
        active_cvm = conn.execute(
            "SELECT COUNT(*) FROM company_map WHERE sit = 'ATIVO'"
        ).fetchone()[0]

        last_log = conn.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        last_sync = last_log["synced_at"] if last_log else "never"
        duration  = last_log["duration_s"] if last_log else 0

        # Age check
        age_warning = ""
        if last_log and last_log["synced_at"]:
            try:
                synced = datetime.fromisoformat(last_log["synced_at"])
                age_days = (datetime.now(timezone.utc) - synced).days
                if age_days > 7:
                    age_warning = f" ⚠ {age_days} days old -- consider re-syncing"
            except Exception:
                pass

        report = (
            f"=== B3-CVM Bridge Status ===\n"
            f"Last sync       : {last_sync}{age_warning}\n"
            f"Sync duration   : {duration}s\n"
            f"Total tickers   : {total:,}\n"
            f"Active (B3)     : {active_b3:,}\n"
            f"Active (CVM)    : {active_cvm:,}\n"
            f"With CVM data   : {with_cvm:,} ({round(with_cvm/total*100,1) if total else 0}%)\n"
            f"With rapina data: {with_rapina:,} ({round(with_rapina/total*100,1) if total else 0}%)\n"
            f"Bridge file     : {path}\n"
        )

        return {
            "status":       "ok",
            "last_sync":    last_sync,
            "total":        total,
            "active_b3":    active_b3,
            "active_cvm":   active_cvm,
            "with_cvm":     with_cvm,
            "with_rapina":  with_rapina,
            "bridge_path":  str(path),
            "report":       report,
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Mode: lookup ──────────────────────────────────────────────────────────────

def mode_lookup(
    ticker: str = "",
    cnpj:   str = "",
    cd_cvm: int = 0,
) -> dict:
    """
    Resolve a company to its full identity record.

    Priority: ticker > cnpj > cd_cvm
    Returns the FIRST matching row (for ticker: all tickers for that CNPJ).

    DECISION: When looking up by ticker, we return ALL tickers for the
    same CNPJ (so the agent knows PETR3 and PETR4 are the same company).
    This is the most useful behavior for cross-skill work:
    "I have PETR4, give me all rapina_ids" -> works regardless of
    whether the user meant ON or PN shares.

    USAGE by other skills:
        from skills.b3.b3_cvm.b3_cvm import mode_lookup
        result = mode_lookup(ticker="PETR4")
        if result["status"] == "success":
            ids = result["rapina_ids"]  # list of ints
            cnpj = result["cnpj"]
            cd_cvm = result["cd_cvm"]
    """
    if not ticker and not cnpj and not cd_cvm:
        return {
            "status": "error",
            "error": "Provide at least one of: ticker, cnpj, cd_cvm",
        }

    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        if ticker:
            # Ticker lookup: find all rows for this ticker, then fetch all
            # sibling tickers that share the same CNPJ
            row = conn.execute(
                "SELECT * FROM company_map WHERE upper(ticker) = ? LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return {
                    "status": "not_found",
                    "error": f"Ticker '{ticker}' not found in bridge.db",
                    "hint": "Run mode='sync' first, or try mode='resolve' with a name.",
                }
            # Use the CNPJ to get all tickers for this company
            query_cnpj = row["cnpj"]

        elif cnpj:
            query_cnpj = _cnpj(cnpj)
            row = conn.execute(
                "SELECT * FROM company_map WHERE cnpj = ? LIMIT 1",
                (query_cnpj,),
            ).fetchone()
            if not row:
                return {"status": "not_found", "error": f"CNPJ '{cnpj}' not found"}

        else:  # cd_cvm
            row = conn.execute(
                "SELECT * FROM company_map WHERE cd_cvm = ? LIMIT 1",
                (int(cd_cvm),),
            ).fetchone()
            if not row:
                return {"status": "not_found", "error": f"CD_CVM {cd_cvm} not found"}
            query_cnpj = row["cnpj"]

        # Get all tickers for this CNPJ
        all_ticker_rows = conn.execute(
            "SELECT ticker, isin, b3_name, b3_sit, b3_type "
            "FROM company_map WHERE cnpj = ? ORDER BY ticker",
            (query_cnpj,),
        ).fetchall()

        tickers = [
            {"ticker": r["ticker"], "isin": r["isin"],
             "name": r["b3_name"], "sit": r["b3_sit"], "type": r["b3_type"]}
            for r in all_ticker_rows
        ]

        rapina_ids = json.loads(row["rapina_ids"] or "[]")

        result = {
            "status":       "success",
            "cnpj":         row["cnpj"],
            "cd_cvm":       row["cd_cvm"],
            "denom_social": row["denom_social"],
            "denom_comerc": row["denom_comerc"],
            "sit":          row["sit"],
            "tp_merc":      row["tp_merc"],
            "setor_ativ":   row["setor_ativ"],
            "tickers":      tickers,              # all B3 tickers for this company
            "rapina_ids":   rapina_ids,           # list of ints, ready for rapina queries
            "synced_at":    row["synced_at"],
        }

        # Human-readable report
        ticker_str = ", ".join(t["ticker"] for t in tickers)
        result["report"] = (
            f"Company    : {row['denom_social']}\n"
            f"Commercial : {row['denom_comerc']}\n"
            f"CNPJ       : {row['cnpj']}\n"
            f"CD_CVM     : {row['cd_cvm']}\n"
            f"Tickers    : {ticker_str}\n"
            f"Status CVM : {row['sit']}\n"
            f"Market     : {row['tp_merc']}\n"
            f"Sector     : {row['setor_ativ']}\n"
            f"rapina_ids : {len(rapina_ids)} empresa rows "
            f"(ids {rapina_ids[0] if rapina_ids else 'n/a'}"
            f"..{rapina_ids[-1] if rapina_ids else 'n/a'})\n"
        )

        return result

    except Exception as e:
        import traceback
        return {"status": "error", "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
    finally:
        conn.close()


# ── Mode: resolve ─────────────────────────────────────────────────────────────

def mode_resolve(query: str = "") -> dict:
    """
    Fuzzy company name search across bridge.db.

    Searches both denom_social and denom_comerc (and b3_name).
    Returns up to 10 unique companies (de-duplicated by CNPJ).

    DECISION: Return one result per CNPJ (not per ticker).
    If "PETROBRAS" matches PETR3 + PETR4 + PETR4F, we return ONE result
    with all three tickers listed. This avoids confusing the agent with
    three near-identical rows.

    USAGE:
        result = mode_resolve(query="ITAU")
        for company in result["companies"]:
            print(company["tickers"], company["cnpj"], company["cd_cvm"])
    """
    if not query or len(query.strip()) < 2:
        return {"status": "error", "error": "query must be at least 2 characters"}

    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        q = f"%{query.upper()}%"

        # Find matching CNPJs from any name field
        matching_cnpjs = conn.execute("""
            SELECT DISTINCT cnpj
            FROM company_map
            WHERE upper(denom_social) LIKE ?
               OR upper(denom_comerc) LIKE ?
               OR upper(b3_name)     LIKE ?
            ORDER BY
                CASE WHEN upper(denom_social) LIKE ? THEN 0 ELSE 1 END,
                denom_social
            LIMIT 10
        """, (q, q, q, q)).fetchall()

        companies = []
        for (cnpj,) in matching_cnpjs:
            # Fetch one representative row + all tickers for that CNPJ
            rep = conn.execute(
                "SELECT * FROM company_map WHERE cnpj = ? LIMIT 1",
                (cnpj,),
            ).fetchone()
            if not rep:
                continue

            all_tickers = conn.execute(
                "SELECT ticker, isin, b3_sit FROM company_map "
                "WHERE cnpj = ? ORDER BY ticker",
                (cnpj,),
            ).fetchall()

            tickers = [
                {"ticker": r["ticker"], "isin": r["isin"], "sit": r["b3_sit"]}
                for r in all_tickers
            ]
            rapina_ids = json.loads(rep["rapina_ids"] or "[]")

            companies.append({
                "cnpj":         rep["cnpj"],
                "cd_cvm":       rep["cd_cvm"],
                "denom_social": rep["denom_social"],
                "denom_comerc": rep["denom_comerc"],
                "sit":          rep["sit"],
                "tp_merc":      rep["tp_merc"],
                "setor_ativ":   rep["setor_ativ"],
                "tickers":      tickers,
                "rapina_ids":   rapina_ids,
            })

        if not companies:
            return {
                "status": "not_found",
                "query":  query,
                "error":  f"No companies found matching '{query}'",
                "hint":   "Try a shorter fragment, e.g. 'PETRO' instead of 'PETROBRAS S.A.'",
            }

        # Build report
        lines = [f"=== Companies matching '{query}' ===", ""]
        for c in companies:
            ticker_str = " / ".join(t["ticker"] for t in c["tickers"])
            lines.append(f"{c['denom_social']}")
            lines.append(f"  CNPJ: {c['cnpj']}  CD_CVM: {c['cd_cvm']}")
            lines.append(f"  Tickers: {ticker_str}  Status: {c['sit']}")
            lines.append(f"  Sector: {c['setor_ativ']}")
            lines.append(f"  rapina_ids: {len(c['rapina_ids'])} rows")
            lines.append("")

        return {
            "status":    "success",
            "query":     query,
            "count":     len(companies),
            "companies": companies,
            "report":    "\n".join(lines),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Mode: tickers ─────────────────────────────────────────────────────────────

def mode_tickers(query: str = "") -> dict:
    """
    List all B3 tickers for a company identified by name fragment or CNPJ.

    Useful to discover the full ticker family:
        PETR3 (ON), PETR4 (PN), PETR4F (fractional), PETRB5 (subscription)...

    Returns structured list with isin, sit, type per ticker.
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    # First resolve by CNPJ or name
    cnpj = _cnpj(query) if re.match(r"^\d{14}$", re.sub(r"\D", "", query)) else ""

    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        if cnpj:
            rows = conn.execute(
                "SELECT ticker, isin, b3_name, b3_sit, b3_type, cnpj, "
                "       denom_social, cd_cvm "
                "FROM company_map WHERE cnpj = ? ORDER BY ticker",
                (cnpj,),
            ).fetchall()
        else:
            q = f"%{query.upper()}%"
            # Find distinct CNPJs matching the name, then get all tickers
            cnpjs = conn.execute("""
                SELECT DISTINCT cnpj FROM company_map
                WHERE upper(denom_social) LIKE ?
                   OR upper(denom_comerc) LIKE ?
                   OR upper(b3_name)      LIKE ?
                LIMIT 5
            """, (q, q, q)).fetchall()

            rows = []
            for (c,) in cnpjs:
                rows += conn.execute(
                    "SELECT ticker, isin, b3_name, b3_sit, b3_type, cnpj, "
                    "       denom_social, cd_cvm "
                    "FROM company_map WHERE cnpj = ? ORDER BY ticker",
                    (c,),
                ).fetchall()

        if not rows:
            return {"status": "not_found", "query": query,
                    "error": f"No tickers found for '{query}'"}

        tickers = [
            {
                "ticker":       r["ticker"],
                "isin":         r["isin"],
                "name":         r["b3_name"],
                "sit":          r["b3_sit"],
                "type":         r["b3_type"],
                "cnpj":         r["cnpj"],
                "denom_social": r["denom_social"],
                "cd_cvm":       r["cd_cvm"],
            }
            for r in rows
        ]

        lines = [f"=== Tickers for '{query}' ===", ""]
        for t in tickers:
            lines.append(
                f"  {t['ticker']:<10} {t['isin']:<14} {t['sit']:<12} {t['type']}"
            )
        lines.append(f"\nTotal: {len(tickers)} tickers")

        return {
            "status":  "success",
            "query":   query,
            "count":   len(tickers),
            "tickers": tickers,
            "report":  "\n".join(lines),
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Public helper for other skills ────────────────────────────────────────────
# These are NOT MCP tools -- they are internal Python imports used by
# cvm_dividends, cvm_shareholders, cvm_api when they need bridge resolution.
#
# DECISION: expose as plain functions (not via dispatcher) so other skill
# modules can do:
#   from skills.b3.b3_cvm.b3_cvm import resolve_by_ticker
# This avoids going through the MCP tool layer for internal calls.

def resolve_by_ticker(ticker: str) -> Optional[dict]:
    """
    Resolve a B3 ticker to its company identity.

    Returns dict with keys: cnpj, cd_cvm, denom_social, denom_comerc,
    sit, tp_merc, rapina_ids (list of ints), tickers (list of dicts).
    Returns None if not found or bridge.db doesn't exist.

    INTENDED CALLERS: cvm_dividends._resolve_company(),
                      cvm_shareholders._resolve_company(),
                      cvm_api queries by ticker

    USAGE PATTERN:
        identity = resolve_by_ticker("PETR4")
        if identity and identity["rapina_ids"]:
            ids = identity["rapina_ids"]
            # use ids in rapina.db queries directly
    """
    result = mode_lookup(ticker=ticker)
    if result.get("status") == "success":
        return result
    return None


def resolve_by_cnpj(cnpj: str) -> Optional[dict]:
    """Resolve by CNPJ (14 digits or formatted). Returns None if not found."""
    result = mode_lookup(cnpj=cnpj)
    if result.get("status") == "success":
        return result
    return None


def resolve_by_cd_cvm(cd_cvm: int) -> Optional[dict]:
    """Resolve by CVM integer code. Returns None if not found."""
    result = mode_lookup(cd_cvm=cd_cvm)
    if result.get("status") == "success":
        return result
    return None


def is_ticker(s: str) -> bool:
    """
    Heuristic: does this string look like a B3 ticker?
    B3 tickers are 4 uppercase letters + 1-2 digits + optional F.
    Examples: PETR4, VALE3, ITUB4, BBAS3, TAEE11, PETR4F
    """
    return bool(re.match(r"^[A-Z]{4}\d{1,2}F?$", s.upper().strip()))
