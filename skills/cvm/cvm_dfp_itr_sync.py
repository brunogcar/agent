"""
skills/cvm/cvm_dfp_itr_sync.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_dfp_itr_sync.py

Shared downloader and parser for CVM DFP and ITR financial statement data.
Replaces what rapinav2 does: downloads CVM ZIPs, parses CSVs, populates dfp_itr.db.

=== CVM DATA ARCHITECTURE ===

Two form types feed dfp_itr.db:

  DFP (Demonstracoes Financeiras Padronizadas) -- ANNUAL
    URL: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip
    Content: full-year financial statements (meses=12)
    Available: last 5 years + historical from 2010 via index
    Updated: weekly

  ITR (Informacoes Trimestrais) -- QUARTERLY
    URL: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip
    Content: Q1 (meses=3), H1 (meses=6), 9M (meses=9) cumulative statements
    Available: last 5 years + historical from 2011
    Updated: weekly

=== ZIP CONTENTS ===

Each ZIP contains multiple CSVs, one per statement type per consolidation:
  dfp_cia_aberta_BPA_con_{year}.csv   -- Balance Sheet Assets (consolidated)
  dfp_cia_aberta_BPA_ind_{year}.csv   -- Balance Sheet Assets (individual)
  dfp_cia_aberta_BPP_con_{year}.csv   -- Balance Sheet Liabilities (consolidated)
  dfp_cia_aberta_DRE_con_{year}.csv   -- Income Statement
  dfp_cia_aberta_DFC_MD_con_{year}.csv -- Cash Flow (direct method)
  dfp_cia_aberta_DFC_MI_con_{year}.csv -- Cash Flow (indirect method)
  dfp_cia_aberta_DVA_con_{year}.csv   -- Value Added Statement
  dfp_cia_aberta_DMPL_con_{year}.csv  -- Changes in Equity
  ... (same pattern for ITR with itr_ prefix)

=== CSV COLUMN MAPPING TO dfp_itr.db ===

CVM CSV column     -> dfp_itr.db column
------------------    -------------------
CNPJ_CIA           -> empresas.cnpj (formatted: "33.000.167/0001-01")
DENOM_CIA          -> empresas.nome
CD_CVM             -> (used to enrich bridge.db cd_cvm if needed)
DT_FIM_EXERC       -> contas.data_fim_exerc (YYYY-MM-DD)
DT_INI_EXERC       -> contas.data_ini_exerc (YYYY-MM-DD)
CD_CONTA           -> contas.codigo
DS_CONTA           -> contas.descr
VL_CONTA           -> contas.valor (raw, multiply by ESCALA_MOEDA for BRL)
ESCALA_MOEDA       -> contas.escala (1 or 1000)
MOEDA              -> contas.moeda (usually "R$")
GRUPO_DFP          -> contas.grupo (BPA, BPP, DRE, DFC, DVA, DMPL)

meses is COMPUTED from DT_INI_EXERC and DT_FIM_EXERC:
  round((DT_FIM_EXERC - DT_INI_EXERC).days / 30.44)
  DFP: always 12. ITR Q1=3, H1=6, 9M=9.

consolidado is INFERRED from filename:
  _con_ -> 1 (consolidated)
  _ind_ -> 0 (individual)

=== DECISION: UPSERT STRATEGY ===
rapinav2 uses hash-based deduplication (hashes table).
We use simpler UPSERT ON CONFLICT for empresas and contas.
This is idempotent: running sync twice produces same result.
Slower than hash check but correct and simpler.

=== DECISION: WHICH FILES TO DOWNLOAD ===
Default: current year + prior year (covers new filings + restatements).
Full history: 2010-present for DFP, 2011-present for ITR.
The full download is ~2-3GB and takes 5-10 minutes.
Incremental (current + prior year only) is ~200MB and takes ~30s.

=== FUTURE SKILLS ===
cvm_ipe: IPE/DADOS/ipe_cia_aberta_{year}.zip -- material events, free text
cvm_fre: FRE/DADOS/fre_cia_aberta_{year}.zip -- reference form (shareholding etc)
Both follow the same download pattern. Parser will differ (different CSV columns).
This file handles DFP+ITR only.
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

CVM_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"

# Statement groups we import. Keys match the filename fragment and CSV GRUPO_DFP values.
# DMPL (Changes in Equity) is verbose and rarely queried -- included but low priority.
STATEMENT_GROUPS = ("BPA", "BPP", "DRE", "DFC_MD", "DFC_MI", "DVA", "DMPL")

# Consolidation suffixes in filenames -> consolidado int value
CONSOLIDATION = {"con": 1, "ind": 0}

# Minimum year available per form type
FIRST_YEAR = {"DFP": 2010, "ITR": 2011, "IPE": 2003, "FRE": 2010}


# ── DB path ───────────────────────────────────────────────────────────────────

def _dfp_itr_db_path() -> Path:
    """
    Path to dfp_itr.db (renamed from rapina.db).
    Uses MEMORY_ROOT env var, same as _db.py pattern.
    """
    import os
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        return Path(memory_root) / "cvm" / "dfp_itr.db"
    # Walk-up fallback
    here = Path(__file__).resolve().parent
    for _ in range(6):
        for sub in ("memory_db/cvm/dfp_itr.db",):
            candidate = here / sub
            if candidate.exists():
                return candidate
        here = here.parent
    # Default: create at MEMORY_ROOT equivalent
    raise FileNotFoundError(
        "Cannot locate memory_db/cvm/. Set MEMORY_ROOT in .env."
    )


def _connect_dfp_itr(read_only: bool = False) -> sqlite3.Connection:
    path = _dfp_itr_db_path()
    if read_only and not path.exists():
        raise FileNotFoundError(f"dfp_itr.db not found at {path}")
    conn = sqlite3.connect(
        f"file:{path}?mode=ro" if read_only else str(path),
        uri=read_only,
    )
    conn.row_factory = sqlite3.Row
    if not read_only:
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create dfp_itr.db schema if it doesn't exist.
    Matches rapinav2's schema exactly so existing data is compatible.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS empresas (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj VARCHAR NOT NULL,
            nome VARCHAR NOT NULL,
            ano  INT     NOT NULL,
            UNIQUE(cnpj, ano)
        );

        CREATE TABLE IF NOT EXISTS contas (
            id_empresa    INTEGER NOT NULL,
            codigo        VARCHAR NOT NULL,
            descr         VARCHAR,
            grupo         VARCHAR,
            consolidado   INTEGER NOT NULL DEFAULT 1,
            data_ini_exerc VARCHAR,
            data_fim_exerc VARCHAR,
            meses         INTEGER,
            valor         REAL,
            escala        INTEGER NOT NULL DEFAULT 1,
            moeda         VARCHAR,
            PRIMARY KEY (id_empresa, codigo, consolidado, data_fim_exerc),
            FOREIGN KEY (id_empresa) REFERENCES empresas(id)
        );

        CREATE INDEX IF NOT EXISTS idx_contas_empresa  ON contas(id_empresa);
        CREATE INDEX IF NOT EXISTS idx_contas_codigo   ON contas(codigo);
        CREATE INDEX IF NOT EXISTS idx_contas_grupo    ON contas(grupo);
        CREATE INDEX IF NOT EXISTS idx_contas_data_fim ON contas(data_fim_exerc);

        CREATE TABLE IF NOT EXISTS tabelas (
            nome    VARCHAR PRIMARY KEY,
            versao  INTEGER NOT NULL DEFAULT 1
        );

        -- Sync state: tracks which (form, year) have been downloaded
        CREATE TABLE IF NOT EXISTS sync_state (
            form       TEXT NOT NULL,
            year       INTEGER NOT NULL,
            synced_at  TEXT NOT NULL,
            rows_added INTEGER DEFAULT 0,
            duration_s REAL DEFAULT 0,
            PRIMARY KEY (form, year)
        );
    """)
    conn.commit()


# ── CNPJ helpers ──────────────────────────────────────────────────────────────

def _cnpj_digits(raw: str) -> str:
    import re
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 14 else digits.zfill(14) if 0 < len(digits) <= 14 else ""


def _compute_meses(dt_ini: str, dt_fim: str) -> int:
    """
    Compute period length in months from date strings (YYYY-MM-DD).
    DFP: always 12. ITR: 3, 6, or 9.

    DECISION: Use calendar month difference (not day count) to avoid
    rounding errors. (date.year - date.year) * 12 + month diff.
    """
    try:
        ini = date.fromisoformat(dt_ini)
        fim = date.fromisoformat(dt_fim)
        months = (fim.year - ini.year) * 12 + (fim.month - ini.month)
        # Round to nearest standard period
        if months <= 4:
            return 3
        elif months <= 7:
            return 6
        elif months <= 10:
            return 9
        else:
            return 12
    except (ValueError, TypeError):
        return 12  # safe default


# ── URL builder ───────────────────────────────────────────────────────────────

def url_for(form: str, year: int) -> str:
    """
    Build CVM download URL for a form/year combination.

    Pattern: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{FORM}/DADOS/{form_lower}_cia_aberta_{year}.zip

    Examples:
      url_for("DFP", 2024) -> .../DFP/DADOS/dfp_cia_aberta_2024.zip
      url_for("ITR", 2025) -> .../ITR/DADOS/itr_cia_aberta_2025.zip
      url_for("IPE", 2024) -> .../IPE/DADOS/ipe_cia_aberta_2024.zip
      url_for("FRE", 2024) -> .../FRE/DADOS/fre_cia_aberta_2024.zip
    """
    form_upper = form.upper()
    form_lower = form.lower()
    return f"{CVM_BASE}/{form_upper}/DADOS/{form_lower}_cia_aberta_{year}.zip"


# ── Download ──────────────────────────────────────────────────────────────────

def download_zip(url: str, timeout: int = 120) -> bytes:
    """
    Download a CVM ZIP file. Returns raw bytes.

    CVM dados.cvm.gov.br is a public HTTP server -- no auth, no special headers.
    Files range from ~5MB (single year ITR) to ~50MB (full DFP history).
    timeout=120s covers slow connections for large files.
    """
    import httpx
    print(f"[dfp_itr_sync] Downloading {url} ...", file=sys.stderr)
    t0 = time.time()
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    elapsed = round(time.time() - t0, 1)
    print(
        f"[dfp_itr_sync] Downloaded {len(resp.content):,} bytes in {elapsed}s",
        file=sys.stderr,
    )
    return resp.content


# ── Parse ─────────────────────────────────────────────────────────────────────

def parse_zip(raw_bytes: bytes, form: str, year: int) -> list[dict]:
    """
    Parse a CVM DFP or ITR ZIP file into a list of row dicts.

    Each dict represents one contas row with all fields needed for upsert:
      cnpj, nome, ano, codigo, descr, grupo, consolidado,
      data_ini_exerc, data_fim_exerc, meses, valor, escala, moeda

    DECISION: Parse ALL CSVs in the ZIP regardless of group name.
    The caller can filter by grupo if needed. Parsing all is simpler
    and ensures no data is silently dropped.

    ENCODING: CVM files use UTF-8 or latin-1. Try UTF-8 first (newer files),
    fallback to latin-1 (older files pre-2019 era).

    DELIMITER: Semicolon (Brazilian CSV standard -- commas are decimal separators).
    """
    if raw_bytes[:2] != b"PK":
        raise ValueError(f"Expected ZIP, got: {raw_bytes[:4]!r}")

    zf  = zipfile.ZipFile(io.BytesIO(raw_bytes))
    all_rows: list[dict] = []

    for entry_name in zf.namelist():
        # Only process CSV data files (not meta/dictionary ZIPs inside)
        if not entry_name.lower().endswith(".csv"):
            continue
        # Skip files that are clearly not financial statement data
        lower = entry_name.lower()
        if "meta_" in lower or "dicion" in lower:
            continue

        # Detect consolidation from filename (_con_ or _ind_)
        consolidado = 1  # default to consolidated
        if "_con_" in lower:
            consolidado = 1
        elif "_ind_" in lower:
            consolidado = 0

        # Detect grupo from filename (BPA, BPP, DRE, DFC_MD, DFC_MI, DVA, DMPL)
        grupo = ""
        for g in ("DFC_MD", "DFC_MI", "DMPL", "BPA", "BPP", "DRE", "DVA"):
            if f"_{g.lower()}_" in lower:
                grupo = g
                break

        # Read and decode CSV content
        raw_csv = zf.read(entry_name)
        content = None
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                content = raw_csv.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            content = raw_csv.decode("latin-1", errors="replace")

        # Parse CSV rows
        reader = csv.DictReader(io.StringIO(content), delimiter=";")
        file_rows = 0
        for csv_row in reader:
            # Map CSV columns to our schema
            cnpj     = csv_row.get("CNPJ_CIA", "").strip()
            nome     = csv_row.get("DENOM_CIA", "").strip()
            dt_ini   = csv_row.get("DT_INI_EXERC", "").strip()
            dt_fim   = csv_row.get("DT_FIM_EXERC", "").strip()
            codigo   = csv_row.get("CD_CONTA", "").strip()
            descr    = csv_row.get("DS_CONTA", "").strip()
            grupo_csv= csv_row.get("GRUPO_DFP", csv_row.get("GRUPO_ITR", grupo)).strip()
            escala   = csv_row.get("ESCALA_MOEDA", "1").strip()
            moeda    = csv_row.get("MOEDA", "R$").strip()
            vl_raw   = csv_row.get("VL_CONTA", "0").strip().replace(",", ".")

            if not cnpj or not codigo:
                continue

            try:
                valor = float(vl_raw) if vl_raw else 0.0
            except ValueError:
                valor = 0.0

            try:
                escala_int = int(float(escala)) if escala else 1
            except ValueError:
                escala_int = 1

            meses = _compute_meses(dt_ini, dt_fim)

            all_rows.append({
                "cnpj":          cnpj,
                "nome":          nome,
                "ano":           year,
                "codigo":        codigo,
                "descr":         descr,
                "grupo":         grupo_csv or grupo,
                "consolidado":   consolidado,
                "data_ini_exerc": dt_ini,
                "data_fim_exerc": dt_fim,
                "meses":         meses,
                "valor":         valor,
                "escala":        escala_int,
                "moeda":         moeda,
            })
            file_rows += 1

        print(
            f"[dfp_itr_sync]   {entry_name}: {file_rows:,} rows "
            f"(consolidado={consolidado}, grupo={grupo or grupo_csv or '?'})",
            file=sys.stderr,
        )

    print(f"[dfp_itr_sync] Total parsed: {len(all_rows):,} rows", file=sys.stderr)
    return all_rows


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """
    Upsert parsed rows into empresas + contas tables.

    Strategy:
      1. Build {(cnpj, ano): empresa_id} cache to avoid N+1 queries
      2. INSERT OR IGNORE into empresas for new company/year combinations
      3. INSERT OR REPLACE into contas (replaces on PK conflict = restatement)

    DECISION: INSERT OR REPLACE for contas (not INSERT OR IGNORE).
    When CVM publishes a restatement, the new data replaces the old.
    rapinav2 uses hash checking to skip unchanged rows -- we keep it simpler
    with upsert. Result is identical for first-time loads; restatements
    correctly overwrite old data.

    Returns number of contas rows inserted/replaced.
    """
    if not rows:
        return 0

    # Step 1: collect unique (cnpj, ano) pairs and upsert empresas
    empresa_keys: set[tuple] = set()
    for r in rows:
        empresa_keys.add((r["cnpj"], r["ano"]))

    conn.executemany(
        "INSERT OR IGNORE INTO empresas (cnpj, nome, ano) VALUES (?, ?, ?)",
        [
            (k[0], next((r["nome"] for r in rows if r["cnpj"]==k[0] and r["ano"]==k[1]), ""), k[1])
            for k in empresa_keys
        ],
    )
    conn.commit()

    # Step 2: build cnpj+ano -> empresa_id cache
    id_cache: dict[tuple, int] = {}
    for cnpj, ano in empresa_keys:
        row = conn.execute(
            "SELECT id FROM empresas WHERE cnpj=? AND ano=?", (cnpj, ano)
        ).fetchone()
        if row:
            id_cache[(cnpj, ano)] = row["id"]

    # Step 3: upsert contas in batches of 10k
    inserted = 0
    batch: list[tuple] = []
    for r in rows:
        emp_id = id_cache.get((r["cnpj"], r["ano"]))
        if not emp_id:
            continue
        batch.append((
            emp_id,
            r["codigo"], r["descr"], r["grupo"], r["consolidado"],
            r["data_ini_exerc"], r["data_fim_exerc"], r["meses"],
            r["valor"], r["escala"], r["moeda"],
        ))
        if len(batch) >= 10_000:
            conn.executemany("""
                INSERT OR REPLACE INTO contas
                    (id_empresa, codigo, descr, grupo, consolidado,
                     data_ini_exerc, data_fim_exerc, meses,
                     valor, escala, moeda)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            inserted += len(batch)
            batch = []

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO contas
                (id_empresa, codigo, descr, grupo, consolidado,
                 data_ini_exerc, data_fim_exerc, meses,
                 valor, escala, moeda)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        inserted += len(batch)

    conn.commit()
    return inserted


# ── Public sync function ──────────────────────────────────────────────────────

def sync(
    form:        str  = "DFP",
    years:       list[int] = None,
    full_history: bool = False,
    force:       bool = False,
) -> dict:
    """
    Download and import CVM financial statement data into dfp_itr.db.

    Args:
        form:         "DFP" (annual) or "ITR" (quarterly). Default: "DFP".
        years:        Specific years to sync. Default: current + prior year.
        full_history: If True, sync all available years (2010-present for DFP).
                      WARNING: ~2-3GB download, 5-10 minutes.
        force:        Re-download even if already synced for this year.

    Returns:
        dict with status, rows_added, duration_s, years_synced

    TYPICAL USAGE:
        # Weekly update (fast, ~30s):
        sync(form="DFP")   # current + prior year DFP
        sync(form="ITR")   # current + prior year ITR

        # Initial setup (slow, ~10 min):
        sync(form="DFP", full_history=True)
        sync(form="ITR", full_history=True)

    DECISION: Sync DFP and ITR separately (not combined).
    DFP is annual -- sync once per year after companies file (April-May).
    ITR is quarterly -- sync after each quarter closes (May, Aug, Nov, Feb).
    Separating them lets the agent update only what changed.
    """
    form  = form.upper()
    if form not in ("DFP", "ITR"):
        return {"status": "error", "error": f"form must be DFP or ITR, got {form!r}"}

    current_year = datetime.now().year

    if full_history:
        years = list(range(FIRST_YEAR[form], current_year + 1))
    elif years:
        years = [int(y) for y in years]
    else:
        # Default: current year + prior year (covers new filings + restatements)
        years = [current_year - 1, current_year]

    print(f"[dfp_itr_sync] Syncing {form} for years: {years}", file=sys.stderr)

    try:
        conn = _connect_dfp_itr(read_only=False)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    t0_total     = time.time()
    total_rows   = 0
    years_synced = []
    years_skipped = []
    errors       = []

    for year in sorted(years):
        # Check if already synced (unless force=True)
        if not force:
            existing = conn.execute(
                "SELECT synced_at, rows_added FROM sync_state WHERE form=? AND year=?",
                (form, year),
            ).fetchone()
            if existing:
                print(
                    f"[dfp_itr_sync] SKIP {form} {year} "
                    f"(synced {existing['synced_at']}, {existing['rows_added']:,} rows). "
                    "Use force=True to re-sync.",
                    file=sys.stderr,
                )
                years_skipped.append(year)
                continue

        url = url_for(form, year)
        t0  = time.time()

        try:
            raw   = download_zip(url)
            rows  = parse_zip(raw, form, year)
            added = upsert_rows(conn, rows)
            duration = round(time.time() - t0, 1)

            # Log sync state
            conn.execute("""
                INSERT OR REPLACE INTO sync_state (form, year, synced_at, rows_added, duration_s)
                VALUES (?, ?, ?, ?, ?)
            """, (form, year, datetime.utcnow().isoformat(), added, duration))
            conn.commit()

            total_rows += added
            years_synced.append(year)
            print(
                f"[dfp_itr_sync] {form} {year}: {added:,} rows in {duration}s",
                file=sys.stderr,
            )

        except Exception as e:
            import traceback
            err = f"{form} {year}: {type(e).__name__}: {e}"
            print(f"[dfp_itr_sync] ERROR {err}", file=sys.stderr)
            errors.append(err)
            # Continue with next year -- don't abort the whole sync

    conn.close()

    total_duration = round(time.time() - t0_total, 1)
    status = "success" if not errors else ("partial" if years_synced else "error")

    report = (
        f"=== DFP/ITR Sync Complete ===\n"
        f"Form           : {form}\n"
        f"Years synced   : {years_synced}\n"
        f"Years skipped  : {years_skipped} (already synced)\n"
        f"Total rows     : {total_rows:,}\n"
        f"Duration       : {total_duration}s\n"
        f"Errors         : {len(errors)}\n"
    )
    if errors:
        report += "Errors:\n" + "\n".join(f"  {e}" for e in errors)

    print(f"[dfp_itr_sync] {report}", file=sys.stderr)

    return {
        "status":        status,
        "form":          form,
        "years_synced":  years_synced,
        "years_skipped": years_skipped,
        "total_rows":    total_rows,
        "duration_s":    total_duration,
        "errors":        errors,
        "report":        report,
    }


def status() -> dict:
    """
    Show dfp_itr.db sync status: which years have been downloaded for each form.
    Quick health check without hitting the network.
    """
    try:
        conn = _connect_dfp_itr(read_only=True)
    except FileNotFoundError:
        return {
            "status":  "not_found",
            "message": "dfp_itr.db not found. Run sync() to populate.",
        }

    try:
        empresas = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        contas   = conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(data_fim_exerc), MAX(data_fim_exerc) FROM contas"
        ).fetchone()
        synced = conn.execute(
            "SELECT form, year, synced_at, rows_added FROM sync_state ORDER BY form, year"
        ).fetchall()
        conn.close()

        by_form: dict[str, list] = {}
        for r in synced:
            by_form.setdefault(r["form"], []).append({
                "year": r["year"], "synced_at": r["synced_at"], "rows": r["rows_added"]
            })

        report_lines = ["=== DFP/ITR DB Status ===", ""]
        for form in sorted(by_form.keys()):
            years = [str(r["year"]) for r in by_form[form]]
            report_lines.append(f"{form}: {', '.join(years)}")
        report_lines += [
            "",
            f"empresas  : {empresas:,} rows",
            f"contas    : {contas:,} rows",
            f"date range: {date_range[0]} to {date_range[1]}",
        ]

        return {
            "status":     "ok",
            "empresas":   empresas,
            "contas":     contas,
            "date_from":  date_range[0],
            "date_to":    date_range[1],
            "by_form":    by_form,
            "report":     "\n".join(report_lines),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
