"""
skills/cvm/cvm_ipe_sync.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_ipe_sync.py

Downloader and parser for CVM IPE (Informacoes Periodicas e Eventuais).
IPE = material events filed by publicly listed companies.
Follows exact same pattern as cvm_dfp_itr_sync.py.

=== WHAT IPE IS ===
Every time a company files a material event with CVM (earnings release,
dividends announcement, board change, M&A, regulatory filing, etc.)
it appears in the IPE dataset as one row with metadata and a download link.

This is the EVENT INDEX -- not the document content itself.
Link_Download points to the actual PDF/XML on CVM's servers.
The skill stores the index; document content retrieval is a future enhancement.

=== IPE CSV COLUMNS (from meta_ipe_cia_aberta.txt, confirmed) ===
CNPJ_Companhia   -> cnpj          (formatted: "33.000.167/0001-01")
Codigo_CVM       -> cd_cvm        (integer string, CVM company code)
Nome_Companhia   -> nome
Data_Entrega     -> data_entrega  (YYYY-MM-DD, when CVM received it)
Data_Referencia  -> data_referencia (YYYY-MM-DD, reference date of event)
Categoria        -> categoria     (high-level type: "Comunicado ao Mercado", etc.)
Tipo             -> tipo          (sub-type: "Aviso aos Acionistas", etc.)
Especie          -> especie       (species: "Ordinaria", etc.)
Assunto          -> assunto       (subject/title of the filing -- free text)
Tipo_Apresentacao-> tipo_apresentacao
Versao           -> versao        (int, document version -- latest > earlier)
Protocolo_Entrega-> protocolo     (unique filing ID -- CVM's internal reference)
Link_Download    -> link_download (URL to the actual document PDF/XML)

=== DB SCHEMA ===
ipe.db -- single table: eventos
  id              INTEGER PK AUTOINCREMENT
  cnpj            VARCHAR  -- digits only after normalization
  cd_cvm          INTEGER
  nome            VARCHAR
  data_entrega    VARCHAR  (YYYY-MM-DD)
  data_referencia VARCHAR  (YYYY-MM-DD)
  categoria       VARCHAR
  tipo            VARCHAR
  especie         VARCHAR
  assunto         TEXT     -- free text, can be long
  tipo_apresentacao VARCHAR
  versao          INTEGER
  protocolo       VARCHAR  -- UNIQUE -- CVM's filing reference
  link_download   VARCHAR
  ano_origem      INTEGER  -- which year's ZIP this came from

UNIQUE KEY on protocolo: prevents duplicate events from overlapping yearly ZIPs.
versao > 1 means a correction was filed -- we keep latest version only.

=== URL PATTERN ===
https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip

One ZIP per year. Each ZIP contains one CSV: ipe_cia_aberta_{year}.csv
Available from 2003 to present. Updated daily.
File size: ~5-15MB per year.

=== DECISION: UPSERT ON CONFLICT(protocolo) ===
Protocolo is CVM's unique filing ID per event. Using it as the dedup key
means re-running sync is idempotent. If CVM corrects an event (versao > 1),
the new row replaces the old via ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

CVM_BASE   = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS"
FIRST_YEAR = 2003   # earliest available IPE year


# ── DB path ───────────────────────────────────────────────────────────────────

def _ipe_db_path() -> Path:
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        return Path(memory_root) / "cvm" / "ipe.db"
    here = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = here / "memory_db" / "cvm" / "ipe.db"
        if candidate.parent.exists():
            return candidate
        here = here.parent
    raise FileNotFoundError("Cannot locate memory_db/cvm/. Set MEMORY_ROOT in .env.")


def _connect_ipe(read_only: bool = False) -> sqlite3.Connection:
    path = _ipe_db_path()
    if read_only and not path.exists():
        raise FileNotFoundError(
            f"ipe.db not found at {path}. Run sync() first."
        )
    conn = sqlite3.connect(
        f"file:{path}?mode=ro" if read_only else str(path),
        uri=read_only,
    )
    conn.row_factory = sqlite3.Row
    if not read_only:
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS eventos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj             VARCHAR NOT NULL,
            cd_cvm           INTEGER DEFAULT 0,
            nome             VARCHAR,
            data_entrega     VARCHAR,
            data_referencia  VARCHAR,
            categoria        VARCHAR,
            tipo             VARCHAR,
            especie          VARCHAR,
            assunto          TEXT,
            tipo_apresentacao VARCHAR,
            versao           INTEGER DEFAULT 1,
            protocolo        VARCHAR NOT NULL,
            link_download    VARCHAR,
            ano_origem       INTEGER,
            UNIQUE(protocolo)
        );

        CREATE INDEX IF NOT EXISTS idx_ipe_cnpj          ON eventos(cnpj);
        CREATE INDEX IF NOT EXISTS idx_ipe_cd_cvm        ON eventos(cd_cvm);
        CREATE INDEX IF NOT EXISTS idx_ipe_data_entrega  ON eventos(data_entrega);
        CREATE INDEX IF NOT EXISTS idx_ipe_categoria     ON eventos(categoria);
        CREATE INDEX IF NOT EXISTS idx_ipe_tipo          ON eventos(tipo);

        CREATE TABLE IF NOT EXISTS sync_state (
            year       INTEGER PRIMARY KEY,
            synced_at  TEXT NOT NULL,
            rows_added INTEGER DEFAULT 0,
            duration_s REAL DEFAULT 0
        );
    """)
    conn.commit()


# ── CNPJ normalization ────────────────────────────────────────────────────────

def _cnpj_digits(raw: str) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 14 else ""


# ── URL builder ───────────────────────────────────────────────────────────────

def url_for(year: int) -> str:
    """
    Build CVM IPE download URL for a given year.
    Pattern: .../IPE/DADOS/ipe_cia_aberta_{year}.zip
    """
    return f"{CVM_BASE}/ipe_cia_aberta_{year}.zip"


# ── Download ──────────────────────────────────────────────────────────────────

def download_zip(url: str, timeout: int = 60) -> bytes:
    import httpx
    print(f"[ipe_sync] Downloading {url} ...", file=sys.stderr)
    t0   = time.time()
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    elapsed = round(time.time() - t0, 1)
    print(f"[ipe_sync] Downloaded {len(resp.content):,} bytes in {elapsed}s",
          file=sys.stderr)
    return resp.content


# ── Parse ─────────────────────────────────────────────────────────────────────

def parse_zip(raw_bytes: bytes, year: int) -> list[dict]:
    """
    Parse IPE ZIP for a given year.

    ZIP contains one CSV: ipe_cia_aberta_{year}.csv
    Delimiter: semicolon. Encoding: UTF-8-BOM or latin-1.

    Returns list of dicts ready for upsert into eventos table.
    """
    if raw_bytes[:2] != b"PK":
        raise ValueError(f"Expected ZIP, got: {raw_bytes[:4]!r}")

    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))

    # Find the data CSV (not metadata files)
    csv_entries = [n for n in zf.namelist()
                   if n.lower().endswith(".csv")
                   and "meta_" not in n.lower()
                   and "dicion" not in n.lower()]

    if not csv_entries:
        raise ValueError(f"No data CSV found in IPE ZIP. Contents: {zf.namelist()}")

    print(f"[ipe_sync] ZIP contains: {zf.namelist()}", file=sys.stderr)

    all_rows: list[dict] = []

    for entry_name in csv_entries:
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

        reader   = csv.DictReader(io.StringIO(content), delimiter=";")
        file_rows = 0
        for row in reader:
            cnpj_raw  = row.get("CNPJ_Companhia", "").strip()
            cd_cvm_raw = row.get("Codigo_CVM", "0").strip()
            protocolo = row.get("Protocolo_Entrega", "").strip()

            if not cnpj_raw or not protocolo:
                continue

            try:
                cd_cvm = int(cd_cvm_raw) if cd_cvm_raw else 0
            except ValueError:
                cd_cvm = 0

            try:
                versao = int(row.get("Versao", "1").strip())
            except ValueError:
                versao = 1

            all_rows.append({
                "cnpj":             _cnpj_digits(cnpj_raw),
                "cd_cvm":           cd_cvm,
                "nome":             row.get("Nome_Companhia", "").strip(),
                "data_entrega":     row.get("Data_Entrega", "").strip(),
                "data_referencia":  row.get("Data_Referencia", "").strip(),
                "categoria":        row.get("Categoria", "").strip(),
                "tipo":             row.get("Tipo", "").strip(),
                "especie":          row.get("Especie", "").strip(),
                "assunto":          row.get("Assunto", "").strip(),
                "tipo_apresentacao":row.get("Tipo_Apresentacao", "").strip(),
                "versao":           versao,
                "protocolo":        protocolo,
                "link_download":    row.get("Link_Download", "").strip(),
                "ano_origem":       year,
            })
            file_rows += 1

        print(f"[ipe_sync]   {entry_name}: {file_rows:,} rows", file=sys.stderr)

    print(f"[ipe_sync] Total parsed: {len(all_rows):,} rows", file=sys.stderr)
    return all_rows


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """
    Upsert into eventos. ON CONFLICT(protocolo) DO UPDATE.

    DECISION: Replace on conflict rather than ignore.
    CVM may issue corrected versions (versao > 1) of the same event.
    The newer row (higher versao or later data_entrega) should win.
    Since we process years in order, newer files overwrite older ones correctly.
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO eventos
            (cnpj, cd_cvm, nome, data_entrega, data_referencia,
             categoria, tipo, especie, assunto, tipo_apresentacao,
             versao, protocolo, link_download, ano_origem)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(protocolo) DO UPDATE SET
            versao           = MAX(versao, excluded.versao),
            data_entrega     = excluded.data_entrega,
            assunto          = excluded.assunto,
            link_download    = excluded.link_download,
            ano_origem       = excluded.ano_origem
    """

    batch_size = 10_000
    inserted   = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        conn.executemany(sql, [
            (r["cnpj"], r["cd_cvm"], r["nome"],
             r["data_entrega"], r["data_referencia"],
             r["categoria"], r["tipo"], r["especie"],
             r["assunto"], r["tipo_apresentacao"],
             r["versao"], r["protocolo"],
             r["link_download"], r["ano_origem"])
            for r in batch
        ])
        inserted += len(batch)

    conn.commit()
    return inserted


# ── Public: sync ──────────────────────────────────────────────────────────────

def sync(
    years:        list[int] = None,
    full_history: bool      = False,
    force:        bool      = False,
) -> dict:
    """
    Download and import CVM IPE event index into ipe.db.

    Args:
        years:        Specific years. Default: current + prior year.
        full_history: All years from 2003. ~50-80MB download, ~2-3 min.
        force:        Re-download even if already synced.

    TYPICAL USAGE:
        sync()                        # current + prior year (~10s)
        sync(years=[2022,2023,2024])  # specific years
        sync(full_history=True)       # all history (~2 min)
    """
    current_year = datetime.now().year

    if full_history:
        years = list(range(FIRST_YEAR, current_year + 1))
    elif years:
        years = [int(y) for y in years]
    else:
        years = [current_year - 1, current_year]

    print(f"[ipe_sync] Syncing IPE for years: {years}", file=sys.stderr)

    try:
        conn = _connect_ipe(read_only=False)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    t0_total      = time.time()
    total_rows    = 0
    years_synced  = []
    years_skipped = []
    errors        = []

    for year in sorted(years):
        if not force:
            existing = conn.execute(
                "SELECT synced_at, rows_added FROM sync_state WHERE year=?",
                (year,),
            ).fetchone()
            if existing:
                print(
                    f"[ipe_sync] SKIP IPE {year} "
                    f"(synced {existing['synced_at']}, {existing['rows_added']:,} rows). "
                    "Use force=True to re-sync.",
                    file=sys.stderr,
                )
                years_skipped.append(year)
                continue

        t0 = time.time()
        try:
            raw      = download_zip(url_for(year))
            rows     = parse_zip(raw, year)
            added    = upsert_rows(conn, rows)
            duration = round(time.time() - t0, 1)

            conn.execute("""
                INSERT OR REPLACE INTO sync_state (year, synced_at, rows_added, duration_s)
                VALUES (?, ?, ?, ?)
            """, (year, datetime.utcnow().isoformat(), added, duration))
            conn.commit()

            total_rows += added
            years_synced.append(year)
            print(f"[ipe_sync] IPE {year}: {added:,} rows in {duration}s",
                  file=sys.stderr)

        except Exception as e:
            err = f"IPE {year}: {type(e).__name__}: {e}"
            print(f"[ipe_sync] ERROR {err}", file=sys.stderr)
            errors.append(err)

    conn.close()

    total_duration = round(time.time() - t0_total, 1)
    status_val     = "success" if not errors else ("partial" if years_synced else "error")

    report = (
        f"=== IPE Sync Complete ===\n"
        f"Years synced   : {years_synced}\n"
        f"Years skipped  : {years_skipped}\n"
        f"Total rows     : {total_rows:,}\n"
        f"Duration       : {total_duration}s\n"
        f"Errors         : {len(errors)}\n"
    )
    if errors:
        report += "\n".join(f"  {e}" for e in errors)

    print(f"[ipe_sync] {report}", file=sys.stderr)
    return {
        "status":        status_val,
        "years_synced":  years_synced,
        "years_skipped": years_skipped,
        "total_rows":    total_rows,
        "duration_s":    total_duration,
        "errors":        errors,
        "report":        report,
    }


# ── Public: status ────────────────────────────────────────────────────────────

def status() -> dict:
    """Show ipe.db sync status and row counts."""
    try:
        conn = _connect_ipe(read_only=True)
    except FileNotFoundError:
        return {"status": "not_synced",
                "message": "ipe.db not found. Run sync() to populate."}
    try:
        total      = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(data_entrega), MAX(data_entrega) FROM eventos"
        ).fetchone()
        synced     = conn.execute(
            "SELECT year, synced_at, rows_added FROM sync_state ORDER BY year"
        ).fetchall()

        # Top categories
        cats = conn.execute("""
            SELECT categoria, COUNT(*) as n FROM eventos
            GROUP BY categoria ORDER BY n DESC LIMIT 5
        """).fetchall()
        conn.close()

        years_list = [r["year"] for r in synced]
        report = (
            f"=== IPE DB Status ===\n"
            f"Synced years   : {years_list}\n"
            f"Total events   : {total:,}\n"
            f"Date range     : {date_range[0]} to {date_range[1]}\n"
            f"Top categories : " +
            ", ".join(f"{r['categoria']}({r['n']:,})" for r in cats) + "\n"
        )
        return {
            "status":     "ok",
            "total":      total,
            "date_from":  date_range[0],
            "date_to":    date_range[1],
            "years":      years_list,
            "report":     report,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Public: query ─────────────────────────────────────────────────────────────

def query(
    company:    str       = "",
    categoria:  str       = "",
    tipo:       str       = "",
    keyword:    str       = "",
    data_from:  str       = "",
    data_to:    str       = "",
    limit:      int       = 20,
    cd_cvm:     int       = 0,
) -> dict:
    """
    Query IPE events for a company or by category/keyword.

    Args:
        company:   Company name fragment, CNPJ (14 digits), or B3 ticker.
                   Tickers resolved via bridge.db if available.
        categoria: Filter by category e.g. "Comunicado ao Mercado".
        tipo:      Filter by tipo e.g. "Aviso aos Acionistas".
        keyword:   Filter by keyword in assunto (subject). Case-insensitive.
        data_from: Start date YYYY-MM-DD for data_entrega filter.
        data_to:   End date YYYY-MM-DD.
        limit:     Max rows to return. Default: 20.
        cd_cvm:    Direct CD_CVM lookup (bypasses name resolution).

    Returns:
        dict with status, events (list), count, report.
    """
    try:
        conn = _connect_ipe(read_only=True)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        conditions = []
        params: list = []

        # Resolve company
        if company:
            from skills.cvm._bridge import looks_like_ticker, resolve_via_bridge
            from skills.cvm._db import cnpj_digits

            cnpj = cnpj_digits(company)
            if cnpj:
                conditions.append("cnpj = ?")
                params.append(cnpj)
            elif looks_like_ticker(company):
                bridge = resolve_via_bridge(company.upper())
                if bridge and bridge[0]:
                    # bridge returns (ids, name) -- we need cnpj from bridge lookup
                    from skills.b3.b3_cvm.b3_cvm import resolve_by_ticker
                    result = resolve_by_ticker(company.upper())
                    if result:
                        conditions.append("cnpj = ?")
                        params.append(result["cnpj"])
                    else:
                        conditions.append("upper(nome) LIKE ?")
                        params.append(f"%{company.upper()}%")
                else:
                    conditions.append("upper(nome) LIKE ?")
                    params.append(f"%{company.upper()}%")
            else:
                conditions.append("upper(nome) LIKE ?")
                params.append(f"%{company.upper()}%")

        if cd_cvm:
            conditions.append("cd_cvm = ?")
            params.append(int(cd_cvm))

        if categoria:
            conditions.append("upper(categoria) LIKE ?")
            params.append(f"%{categoria.upper()}%")

        if tipo:
            conditions.append("upper(tipo) LIKE ?")
            params.append(f"%{tipo.upper()}%")

        if keyword:
            conditions.append("upper(assunto) LIKE ?")
            params.append(f"%{keyword.upper()}%")

        if data_from:
            conditions.append("data_entrega >= ?")
            params.append(data_from)

        if data_to:
            conditions.append("data_entrega <= ?")
            params.append(data_to)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = conn.execute(f"""
            SELECT cnpj, cd_cvm, nome, data_entrega, data_referencia,
                   categoria, tipo, especie, assunto,
                   versao, protocolo, link_download
            FROM eventos
            {where}
            ORDER BY data_entrega DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        events = [dict(r) for r in rows]

        if not events:
            return {
                "status": "not_found",
                "error":  f"No IPE events found for the given filters.",
                "count":  0,
                "events": [],
                "report": "Nenhum evento IPE encontrado para os filtros informados.",
            }

        # Human-readable report
        lines = [
            f"=== IPE Events ({len(events)} results) ===",
            f"Filters: company={company!r} categoria={categoria!r} keyword={keyword!r}",
            "",
        ]
        for e in events:
            lines.append(
                f"{e['data_entrega']}  {e['nome'][:35]:<35}  "
                f"{e['categoria'][:30]:<30}  {e['assunto'][:60]}"
            )

        return {
            "status": "success",
            "count":  len(events),
            "events": events,
            "report": "\n".join(lines),
        }

    except Exception as e:
        import traceback
        return {"status": "error", "error": str(e),
                "traceback": traceback.format_exc()}
    finally:
        conn.close()