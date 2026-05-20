"""
skills/b3/b3_cvm/b3_cvm.py -- B3-CVM company identity bridge.

Deploy to: D:\mcp\agent\skills\b3\b3_cvm\b3_cvm.py

=== WHAT THIS FILE DOES ===
Builds and queries bridge.db, a local SQLite database that maps:

    TICKER (B3) <-> ISIN <-> CNPJ <-> CD_CVM (CVM) <-> rapina_ids

This solves the cross-skill identity problem: every other skill identifies
companies differently (ticker, CD_CVM, rapina empresa.id, name), and without
a bridge they cannot talk to each other.

=== BUG FIX v2: B3 ISIN FILE IS A ZIP ===
The GetFileDownload endpoint returns a ZIP file, not raw TXT.
Magic bytes PK (0x50 0x4B) at the start of the response confirm this.
v1 decoded the raw ZIP bytes as latin-1 text, passed garbled data to the
parser, got 15k rows with all-empty CNPJs (ZIP data chunks with pipe chars).
FIX: detect ZIP magic, unzip in memory, decode the inner TXT file.

=== B3 ISIN FILE COLUMN STRUCTURE (confirmed from header inspection) ===
The inner TXT after unzipping is pipe-delimited with these columns
(from B3 ISIN page documentation and rapinav2 README):
  Codigo ISIN | Codigo Instrumento | Descricao Instrumento |
  Situacao Instrumento | Data Inicio Vigencia | Data Fim Vigencia |
  Tipo Ativo | CNPJ | ...
Column names may vary slightly -- we parse by header name with fallback
to positional parsing if header detection fails.

=== DATA SOURCES ===

1. B3 ISIN file (ZIP, downloaded fresh each sync):
   GET .../IsinCall/GetTextDownload/  => JSON {geralPt: {id, dataGeracao}}
   base64(json.dumps(id))            => encoded file ID
   GET .../IsinCall/GetFileDownload/{encoded_id} => ZIP file
   Unzip => pipe-delimited TXT, ~15k rows

2. CVM cad_cia_aberta.csv (downloaded fresh each sync):
   GET https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
   Semicolon-delimited, ~2,673 rows (2026-05 count confirmed)

3. rapina.db (already local, read-only):
   1,218 unique CNPJs, 10,840 empresa rows (confirmed from verify output)

=== CNPJ NORMALIZATION ===
All sources use different formats:
  B3:      may be formatted "33.000.167/0001-01" or digits-only
  CVM CSV: "33.000.167/0001-01" (punctuated)
  rapina:  "33000167000101" (digits only)
Strip all non-digits -> 14-char string as the universal join key.

=== BRIDGE.DB SCHEMA ===
One row per (ticker, isin). Same company -> multiple rows (PETR3 + PETR4 etc).

=== DECISION: cvm_api and cvm_register also get bridge lookup ===
Both skills use empresa resolution by name/CNPJ. Adding ticker resolution
via bridge makes them usable with B3 tickers just like dividends/shareholders.
The resolve_by_ticker() / resolve_by_cnpj() helper functions at the bottom
of this file are the shared interface for all cvm_* skills.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Path helpers ──────────────────────────────────────────────────────────────

def _cvm_dir() -> Path:
    """Return memory_db/cvm/ directory. Uses MEMORY_ROOT env var."""
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        d = Path(memory_root) / "cvm"
        d.mkdir(parents=True, exist_ok=True)
        return d
    # Walk up from this file
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
    """Strip non-digits. Returns 14-char string or '' if wrong length."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else ""


# ── Bridge DB ─────────────────────────────────────────────────────────────────

def _bridge_conn(read_only: bool = False) -> sqlite3.Connection:
    path = _bridge_path()
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
            CREATE INDEX IF NOT EXISTS idx_bridge_cnpj   ON company_map(cnpj);
            CREATE INDEX IF NOT EXISTS idx_bridge_cd_cvm ON company_map(cd_cvm);
            CREATE INDEX IF NOT EXISTS idx_bridge_ticker ON company_map(ticker);
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
    Download B3 ISIN file (ZIP) and return parsed rows.

    CRITICAL FIX (v2): The response is a ZIP file, not raw TXT.
    PK magic bytes at offset 0 confirm this. We must unzip in memory
    before decoding. v1 decoded raw ZIP bytes as latin-1 text which
    produced 15k garbled rows with all-empty CNPJs.

    The ZIP contains exactly one file (the pipe-delimited TXT).
    We read the first (and only) entry regardless of its filename.
    """
    import httpx

    # Browser-like headers required -- B3 API checks Referer/Origin
    headers = {
        "User-Agent":  (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":      "application/json, text/plain, */*",
        "Referer":     "https://sistemaswebb3-listados.b3.com.br/isinPage",
        "Origin":      "https://sistemaswebb3-listados.b3.com.br",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    # Step 1: get file index
    index_url = (
        "https://sistemaswebb3-listados.b3.com.br"
        "/isinProxy/IsinCall/GetTextDownload/"
    )
    print("[b3_cvm] Fetching B3 ISIN file index...", file=sys.stderr)
    resp = httpx.get(index_url, headers=headers, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    index = resp.json()

    file_id  = index["geralPt"]["id"]
    gen_date = index["geralPt"].get("dataGeracao", "")
    print(f"[b3_cvm] B3 ISIN geralPt id={file_id}, generated={gen_date}", file=sys.stderr)

    # Step 2: base64-encode the integer (btoa(JSON.stringify(id)) in JS)
    encoded_id = base64.b64encode(json.dumps(file_id).encode()).decode()

    # Step 3: download ZIP
    file_url = (
        f"https://sistemaswebb3-listados.b3.com.br"
        f"/isinProxy/IsinCall/GetFileDownload/{encoded_id}"
    )
    print(f"[b3_cvm] Downloading B3 ISIN ZIP ({encoded_id})...", file=sys.stderr)
    resp = httpx.get(file_url, headers=headers, timeout=60, follow_redirects=True)
    resp.raise_for_status()

    raw_bytes = resp.content
    print(f"[b3_cvm] Downloaded {len(raw_bytes):,} bytes", file=sys.stderr)

    # Step 4: unzip if ZIP (magic bytes PK = 0x50 0x4B)
    # DECISION: Always check for ZIP magic. If B3 ever switches to raw TXT,
    # the fallback handles it gracefully without breaking the sync.
    if raw_bytes[:2] == b"PK":
        print("[b3_cvm] Response is ZIP -- extracting inner file...", file=sys.stderr)
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
            inner_name = zf.namelist()[0]
            print(f"[b3_cvm] ZIP contains: {zf.namelist()}", file=sys.stderr)
            raw_bytes = zf.read(inner_name)
            print(f"[b3_cvm] Inner file: {len(raw_bytes):,} bytes", file=sys.stderr)
        except zipfile.BadZipFile as e:
            raise ValueError(f"B3 file looks like ZIP but could not be opened: {e}")
    else:
        print("[b3_cvm] Response is raw TXT (not ZIP)", file=sys.stderr)

    # Step 5: decode text
    # DECISION: Try latin-1 first -- B3 files historically use ISO-8859-1.
    # latin-1 is a strict superset of ASCII and handles all byte values 0-255
    # without raising exceptions. utf-8 may fail on accented chars.
    content = None
    for encoding in ("latin-1", "utf-8", "cp1252"):
        try:
            content = raw_bytes.decode(encoding)
            print(f"[b3_cvm] Decoded with {encoding}", file=sys.stderr)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode("latin-1", errors="replace")

    return _parse_b3_isin_content(content)


def _parse_b3_isin_content(content: str) -> list[dict]:
    """
    Parse pipe-delimited B3 ISIN file content.

    Expected header columns (from B3 ISIN page + rapinav2 README):
      Codigo ISIN | Codigo Instrumento | Descricao Instrumento |
      Situacao Instrumento | Data Inicio Vigencia | Data Fim Vigencia |
      Tipo Ativo | CNPJ Emissor | ...

    DECISION: Parse header by normalized name (lowercase, strip accents)
    so minor column name variations don't break parsing.
    Fallback: positional (0=ISIN, 1=Codigo Instrumento/ticker).

    CNPJ: B3 ISIN file may have CNPJ in column "CNPJ Emissor" or "CNPJ".
    We normalize to 14-digit digits-only format for joining.
    """
    lines = content.splitlines()
    if not lines:
        return []

    header_line = lines[0]
    sep = "|"
    headers = [h.strip() for h in header_line.split(sep)]

    def _norm(s: str) -> str:
        """Normalize header: lowercase, strip accents, collapse spaces."""
        s = s.lower().strip()
        for a, b in [
            ("ã", "a"), ("â", "a"), ("á", "a"), ("à", "a"),
            ("ç", "c"), ("é", "e"), ("ê", "e"), ("è", "e"),
            ("ó", "o"), ("ô", "o"), ("ú", "u"), ("ü", "u"),
            ("í", "i"), ("î", "i"),
        ]:
            s = s.replace(a, b)
        return re.sub(r"\s+", "_", s)

    norm_headers = [_norm(h) for h in headers]
    print(f"[b3_cvm] Header columns: {headers[:8]}", file=sys.stderr)

    def _col(*candidates: str) -> int:
        for c in candidates:
            nc = _norm(c)
            if nc in norm_headers:
                return norm_headers.index(nc)
        return -1

    idx_isin   = _col("Codigo ISIN", "ISIN", "Codigo_ISIN")
    idx_ticker = _col("Codigo Instrumento", "Codigo do Instrumento", "Ticker", "Instrumento")
    idx_name   = _col("Descricao Instrumento", "Descricao do Instrumento", "Descricao", "Nome")
    idx_sit    = _col("Situacao Instrumento", "Situacao", "Sit")
    idx_type   = _col("Tipo Ativo", "Tipo Mercado", "Tipo")
    idx_cnpj   = _col("CNPJ Emissor", "CNPJ", "CNPJ_Emissor")

    print(
        f"[b3_cvm] Column indices: isin={idx_isin} ticker={idx_ticker} "
        f"name={idx_name} sit={idx_sit} type={idx_type} cnpj={idx_cnpj}",
        file=sys.stderr,
    )

    # Warn but don't abort if positional fallback needed
    if idx_isin == -1 or idx_ticker == -1:
        print(
            f"[b3_cvm] WARNING: Header detection failed -- using positional "
            f"(0=ISIN, 1=ticker). Header: {headers[:6]}",
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

        if not isin or len(isin) < 10:
            continue
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

    # Diagnostic: how many had a CNPJ
    with_cnpj = sum(1 for r in rows if r["cnpj"])
    print(
        f"[b3_cvm] Parsed {len(rows):,} rows | with CNPJ: {with_cnpj:,} "
        f"| no CNPJ: {len(rows)-with_cnpj:,}",
        file=sys.stderr,
    )

    # If still 0 CNPJs, print a sample row for debugging
    if with_cnpj == 0 and rows:
        sample_line = lines[1] if len(lines) > 1 else "(none)"
        print(
            f"[b3_cvm] DEBUG: sample row (line 1): {repr(sample_line[:300])}",
            file=sys.stderr,
        )

    return rows


# ── CVM cad_cia_aberta.csv download ──────────────────────────────────────────

def _fetch_cvm_register() -> list[dict]:
    """
    Download CVM cad_cia_aberta.csv (semicolon-delimited, ~2,673 rows).

    URL: https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv

    Key columns: CD_CVM | CNPJ_CIA | DENOM_SOCIAL | DENOM_COMERC |
                 SIT | TP_MERC | SETOR_ATIV
    CNPJ_CIA is punctuated ("33.000.167/0001-01") -- normalize via _cnpj().

    DECISION: Include CANCELADO/SUSPENSO companies because rapina.db has
    historical data for them (e.g. merged companies before cancellation).
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

    DECISION: Parse by header column name (not position) so CVM adding
    new columns in future doesn't break the parser.
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
        cnpj_raw   = _get(parts, "CNPJ_CIA")
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


# ── rapina.db CNPJ -> empresa.id mapping ─────────────────────────────────────

def _build_rapina_index() -> dict[str, list[int]]:
    """
    Build {cnpj: [empresa_id, ...]} from rapina.db.

    DECISION: Collect ALL ids for each CNPJ (not just most recent).
    One company can have 40+ ids (one per quarterly period over 10 years).
    The consuming skill decides which ids to use based on dt_refer filtering.
    Sorted ascending so [0]=oldest, [-1]=newest.
    """
    try:
        rapina = _rapina_path()
    except FileNotFoundError as e:
        print(f"[b3_cvm] WARNING: {e}. rapina_ids will be empty.", file=sys.stderr)
        return {}

    conn = sqlite3.connect(f"file:{rapina}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, cnpj FROM empresas "
            "WHERE cnpj IS NOT NULL AND cnpj != '' ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()

    index: dict[str, list[int]] = {}
    for empresa_id, raw_cnpj in rows:
        cnpj = _cnpj(str(raw_cnpj))
        if cnpj:
            index.setdefault(cnpj, []).append(empresa_id)

    for cnpj in index:
        index[cnpj] = sorted(set(index[cnpj]))

    total_ids = sum(len(v) for v in index.values())
    print(
        f"[b3_cvm] rapina index: {len(index):,} CNPJs | {total_ids:,} empresa rows",
        file=sys.stderr,
    )
    return index


# ── Mode: sync ────────────────────────────────────────────────────────────────

def mode_sync() -> dict:
    """
    Build/rebuild bridge.db from B3 ISIN (ZIP) + CVM CSV + rapina.db.

    Steps:
      1. Download B3 ISIN ZIP -> unzip -> parse pipe-delimited TXT
      2. Download CVM cad_cia_aberta.csv -> parse
      3. Read rapina.db -> build {cnpj: [empresa_ids]} index
      4. Join all three on CNPJ -> UPSERT into bridge.db company_map
      5. Log result to sync_log table

    Returns summary dict with counts and coverage statistics.
    """
    import time
    t0 = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        b3_rows = _fetch_b3_isin_file()
    except Exception as e:
        return {"status": "error", "error": f"B3 ISIN download failed: {e}", "step": "b3"}

    try:
        cvm_rows = _fetch_cvm_register()
    except Exception as e:
        return {"status": "error", "error": f"CVM CSV download failed: {e}", "step": "cvm"}

    rapina_index = _build_rapina_index()

    # Build CVM lookup {cnpj -> row}, preferring ATIVO when duplicates exist
    cvm_by_cnpj: dict[str, dict] = {}
    for row in cvm_rows:
        cnpj = row["cnpj"]
        if not cnpj:
            continue
        existing = cvm_by_cnpj.get(cnpj)
        if existing is None or (
            row.get("sit") == "ATIVO" and existing.get("sit") != "ATIVO"
        ):
            cvm_by_cnpj[cnpj] = row

    conn = _bridge_conn(read_only=False)
    try:
        matched  = 0
        no_cnpj  = 0
        inserted = 0

        for b3 in b3_rows:
            cnpj = b3["cnpj"]
            if not cnpj:
                no_cnpj += 1
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
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker, isin) DO UPDATE SET
                    b3_name=excluded.b3_name, b3_sit=excluded.b3_sit,
                    b3_type=excluded.b3_type, cnpj=excluded.cnpj,
                    cd_cvm=excluded.cd_cvm, denom_social=excluded.denom_social,
                    denom_comerc=excluded.denom_comerc, sit=excluded.sit,
                    tp_merc=excluded.tp_merc, setor_ativ=excluded.setor_ativ,
                    rapina_ids=excluded.rapina_ids, synced_at=excluded.synced_at
            """, (
                b3["ticker"], b3["isin"], b3["name"], b3["sit"], b3["type"],
                cnpj,
                cvm.get("cd_cvm", 0), cvm.get("denom_social", ""),
                cvm.get("denom_comerc", ""), cvm.get("sit", ""),
                cvm.get("tp_merc", ""), cvm.get("setor_ativ", ""),
                json.dumps(rapina_ids), now_iso,
            ))
            inserted += 1

        conn.commit()

        total       = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm    = conn.execute("SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0").fetchone()[0]
        with_rapina = conn.execute("SELECT COUNT(*) FROM company_map WHERE rapina_ids != '[]'").fetchone()[0]
        duration    = round(time.time() - t0, 1)

        conn.execute(
            "INSERT INTO sync_log (synced_at,b3_rows,cvm_rows,bridge_rows,matched,duration_s,notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (now_iso, len(b3_rows), len(cvm_rows), total, matched, duration, f"no_cnpj={no_cnpj}"),
        )
        conn.commit()
    finally:
        conn.close()

    coverage_pct = round(with_cvm    / total * 100, 1) if total else 0
    rapina_pct   = round(with_rapina / total * 100, 1) if total else 0

    report = (
        f"=== B3-CVM Bridge Sync Complete ===\n"
        f"Duration        : {duration}s\n"
        f"B3 ISIN rows    : {len(b3_rows):,}\n"
        f"CVM register    : {len(cvm_rows):,}\n"
        f"Bridge total    : {total:,} tickers\n"
        f"B3 + CVM match  : {with_cvm:,} ({coverage_pct}%)\n"
        f"B3 + rapina     : {with_rapina:,} ({rapina_pct}%)\n"
        f"No CNPJ         : {no_cnpj:,}\n"
        f"Synced at       : {now_iso}\n"
    )
    print(f"[b3_cvm] {report}", file=sys.stderr)

    return {
        "status": "success",
        "b3_rows": len(b3_rows), "cvm_rows": len(cvm_rows),
        "bridge_total": total, "with_cvm": with_cvm,
        "with_rapina": with_rapina, "no_cnpj": no_cnpj,
        "coverage_pct": coverage_pct, "rapina_pct": rapina_pct,
        "duration_s": duration, "synced_at": now_iso, "report": report,
    }


# ── Mode: status ──────────────────────────────────────────────────────────────

def mode_status() -> dict:
    path = _bridge_path()
    if not path.exists():
        return {
            "status": "not_synced",
            "message": "bridge.db not found. Run skill(domain='b3_cvm', mode='sync').",
        }
    try:
        conn  = _bridge_conn(read_only=True)
        total       = conn.execute("SELECT COUNT(*) FROM company_map").fetchone()[0]
        with_cvm    = conn.execute("SELECT COUNT(*) FROM company_map WHERE cd_cvm > 0").fetchone()[0]
        with_rapina = conn.execute("SELECT COUNT(*) FROM company_map WHERE rapina_ids != '[]'").fetchone()[0]
        active_b3   = conn.execute("SELECT COUNT(*) FROM company_map WHERE upper(b3_sit) LIKE '%ATIVO%'").fetchone()[0]
        last_log    = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        last_sync = last_log["synced_at"] if last_log else "never"
        duration  = last_log["duration_s"] if last_log else 0

        age_warning = ""
        if last_log and last_log["synced_at"]:
            try:
                synced  = datetime.fromisoformat(last_log["synced_at"])
                age_days = (datetime.now(timezone.utc) - synced).days
                if age_days > 7:
                    age_warning = f" [{age_days}d old -- consider re-syncing]"
            except Exception:
                pass

        report = (
            f"=== B3-CVM Bridge Status ===\n"
            f"Last sync       : {last_sync}{age_warning}\n"
            f"Sync duration   : {duration}s\n"
            f"Total tickers   : {total:,}\n"
            f"Active (B3)     : {active_b3:,}\n"
            f"With CVM data   : {with_cvm:,} ({round(with_cvm/total*100,1) if total else 0}%)\n"
            f"With rapina data: {with_rapina:,} ({round(with_rapina/total*100,1) if total else 0}%)\n"
            f"Bridge file     : {path}\n"
        )
        return {
            "status": "ok", "last_sync": last_sync, "total": total,
            "active_b3": active_b3, "with_cvm": with_cvm,
            "with_rapina": with_rapina, "bridge_path": str(path),
            "report": report,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Mode: lookup ──────────────────────────────────────────────────────────────

def mode_lookup(ticker: str = "", cnpj: str = "", cd_cvm: int = 0) -> dict:
    """
    Resolve company by ticker, CNPJ, or CD_CVM to full identity record.

    Returns all tickers for the same CNPJ (PETR3 + PETR4 + PETR4F etc)
    and the pre-computed rapina_ids list for direct use in rapina queries.
    """
    if not ticker and not cnpj and not cd_cvm:
        return {"status": "error", "error": "Provide ticker, cnpj, or cd_cvm"}

    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        if ticker:
            row = conn.execute(
                "SELECT * FROM company_map WHERE upper(ticker)=? LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return {"status": "not_found",
                        "error": f"Ticker '{ticker}' not found in bridge.db"}
            query_cnpj = row["cnpj"]

        elif cnpj:
            query_cnpj = _cnpj(cnpj)
            row = conn.execute(
                "SELECT * FROM company_map WHERE cnpj=? LIMIT 1",
                (query_cnpj,),
            ).fetchone()
            if not row:
                return {"status": "not_found",
                        "error": f"CNPJ '{cnpj}' not found in bridge.db"}

        else:
            row = conn.execute(
                "SELECT * FROM company_map WHERE cd_cvm=? LIMIT 1",
                (int(cd_cvm),),
            ).fetchone()
            if not row:
                return {"status": "not_found",
                        "error": f"CD_CVM {cd_cvm} not found in bridge.db"}
            query_cnpj = row["cnpj"]

        # All tickers sharing the same CNPJ
        all_rows = conn.execute(
            "SELECT ticker, isin, b3_name, b3_sit, b3_type "
            "FROM company_map WHERE cnpj=? ORDER BY ticker",
            (query_cnpj,),
        ).fetchall()

        tickers    = [{"ticker": r["ticker"], "isin": r["isin"],
                       "name": r["b3_name"], "sit": r["b3_sit"],
                       "type": r["b3_type"]} for r in all_rows]
        rapina_ids = json.loads(row["rapina_ids"] or "[]")

        result = {
            "status": "success",
            "cnpj": row["cnpj"], "cd_cvm": row["cd_cvm"],
            "denom_social": row["denom_social"], "denom_comerc": row["denom_comerc"],
            "sit": row["sit"], "tp_merc": row["tp_merc"],
            "setor_ativ": row["setor_ativ"],
            "tickers": tickers, "rapina_ids": rapina_ids,
            "synced_at": row["synced_at"],
        }
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
            f"rapina_ids : {len(rapina_ids)} rows\n"
        )
        return result

    except Exception as e:
        import traceback
        return {"status": "error", "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
    finally:
        conn.close()


# ── Mode: resolve ─────────────────────────────────────────────────────────────

def mode_resolve(query: str = "") -> dict:
    """Fuzzy name search. Returns up to 10 companies (one per CNPJ)."""
    if not query or len(query.strip()) < 2:
        return {"status": "error", "error": "query must be at least 2 characters"}
    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    try:
        q = f"%{query.upper()}%"
        cnpj_rows = conn.execute("""
            SELECT DISTINCT cnpj FROM company_map
            WHERE upper(denom_social) LIKE ? OR upper(denom_comerc) LIKE ?
               OR upper(b3_name)      LIKE ?
            ORDER BY CASE WHEN upper(denom_social) LIKE ? THEN 0 ELSE 1 END, denom_social
            LIMIT 10
        """, (q, q, q, q)).fetchall()

        companies = []
        for (cnpj,) in cnpj_rows:
            rep = conn.execute(
                "SELECT * FROM company_map WHERE cnpj=? LIMIT 1", (cnpj,)
            ).fetchone()
            if not rep:
                continue
            all_tickers = conn.execute(
                "SELECT ticker, isin, b3_sit FROM company_map WHERE cnpj=? ORDER BY ticker",
                (cnpj,),
            ).fetchall()
            companies.append({
                "cnpj": rep["cnpj"], "cd_cvm": rep["cd_cvm"],
                "denom_social": rep["denom_social"], "denom_comerc": rep["denom_comerc"],
                "sit": rep["sit"], "tp_merc": rep["tp_merc"], "setor_ativ": rep["setor_ativ"],
                "tickers": [{"ticker": r["ticker"], "isin": r["isin"], "sit": r["b3_sit"]}
                            for r in all_tickers],
                "rapina_ids": json.loads(rep["rapina_ids"] or "[]"),
            })

        if not companies:
            return {"status": "not_found", "query": query,
                    "error": f"No companies found matching '{query}'"}

        lines = [f"=== Companies matching '{query}' ===", ""]
        for c in companies:
            tstr = " / ".join(t["ticker"] for t in c["tickers"])
            lines += [
                f"{c['denom_social']}",
                f"  CNPJ: {c['cnpj']}  CD_CVM: {c['cd_cvm']}",
                f"  Tickers: {tstr}  Status: {c['sit']}",
                f"  rapina_ids: {len(c['rapina_ids'])} rows", "",
            ]
        return {
            "status": "success", "query": query, "count": len(companies),
            "companies": companies, "report": "\n".join(lines),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Mode: tickers ─────────────────────────────────────────────────────────────

def mode_tickers(query: str = "") -> dict:
    """List all B3 tickers for a company (name fragment or CNPJ)."""
    if not query:
        return {"status": "error", "error": "query is required"}
    try:
        conn = _bridge_conn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    try:
        cnpj_clean = _cnpj(re.sub(r"\D", "", query))
        if cnpj_clean:
            rows = conn.execute(
                "SELECT ticker, isin, b3_name, b3_sit, b3_type, cnpj, denom_social, cd_cvm "
                "FROM company_map WHERE cnpj=? ORDER BY ticker", (cnpj_clean,)
            ).fetchall()
        else:
            q = f"%{query.upper()}%"
            cnpjs = conn.execute(
                "SELECT DISTINCT cnpj FROM company_map "
                "WHERE upper(denom_social) LIKE ? OR upper(denom_comerc) LIKE ? "
                "   OR upper(b3_name) LIKE ? LIMIT 5", (q, q, q)
            ).fetchall()
            rows = []
            for (c,) in cnpjs:
                rows += conn.execute(
                    "SELECT ticker, isin, b3_name, b3_sit, b3_type, cnpj, denom_social, cd_cvm "
                    "FROM company_map WHERE cnpj=? ORDER BY ticker", (c,)
                ).fetchall()

        if not rows:
            return {"status": "not_found", "query": query,
                    "error": f"No tickers found for '{query}'"}

        tickers = [{"ticker": r["ticker"], "isin": r["isin"], "name": r["b3_name"],
                    "sit": r["b3_sit"], "type": r["b3_type"], "cnpj": r["cnpj"],
                    "denom_social": r["denom_social"], "cd_cvm": r["cd_cvm"]}
                   for r in rows]
        lines = [f"=== Tickers for '{query}' ===", ""]
        for t in tickers:
            lines.append(f"  {t['ticker']:<10} {t['isin']:<14} {t['sit']:<12} {t['type']}")
        lines.append(f"\nTotal: {len(tickers)} tickers")
        return {"status": "success", "query": query, "count": len(tickers),
                "tickers": tickers, "report": "\n".join(lines)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


# ── Public helpers (imported by cvm_* skills) ─────────────────────────────────
# These are NOT MCP tools -- plain Python functions for internal skill imports.
# Usage in cvm_dividends, cvm_shareholders, cvm_api, cvm_register:
#   from skills.b3.b3_cvm.b3_cvm import resolve_by_ticker
#   identity = resolve_by_ticker("PETR4")
#   if identity:
#       ids = identity["rapina_ids"]   # list[int], ready for rapina queries
#       cnpj = identity["cnpj"]
#       cd_cvm = identity["cd_cvm"]

def resolve_by_ticker(ticker: str) -> Optional[dict]:
    """Return full identity dict for a ticker, or None if not found/bridge missing."""
    r = mode_lookup(ticker=ticker)
    return r if r.get("status") == "success" else None


def resolve_by_cnpj(cnpj: str) -> Optional[dict]:
    """Return full identity dict for a CNPJ, or None if not found."""
    r = mode_lookup(cnpj=cnpj)
    return r if r.get("status") == "success" else None


def resolve_by_cd_cvm(cd_cvm: int) -> Optional[dict]:
    """Return full identity dict for a CD_CVM code, or None if not found."""
    r = mode_lookup(cd_cvm=cd_cvm)
    return r if r.get("status") == "success" else None


def is_ticker(s: str) -> bool:
    """True if s looks like a B3 ticker: 4 letters + 1-2 digits + optional F."""
    return bool(re.match(r"^[A-Z]{4}\d{1,2}F?$", s.upper().strip()))
