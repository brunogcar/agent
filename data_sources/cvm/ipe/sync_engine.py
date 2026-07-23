"""data_sources/cvm/ipe/sync_engine.py -- Download IPE ZIPs and populate ipe.db.

IPE = Informações Periódicas e Eventuais (material events index).
Simplest CVM data source: single table (eventos), single CSV per ZIP.

DEDUP: Uses Protocolo_Entrega as unique key (CVM's filing reference).
Re-syncing is idempotent — same event always maps to same row.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from core.tracer import tracer
from data_sources.cvm._db import connect_ipe, ipe_db_path, cnpj_digits
from data_sources.cvm.ipe.catalog import (
    URL_PATTERN, FIRST_YEAR, CSV_ENCODING, CSV_DELIMITER, SCHEMA_SQL, CSV_COLUMNS,
)


def sync(
    years: list[int] | None = None,
    full_history: bool = False,
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download IPE ZIPs and populate ipe.db.

    Args:
        years: Specific years to sync. Default: current year.
        full_history: Sync all years from FIRST_YEAR (2003) to current.
        force: Re-download even if already synced.
        trace_id: Tracer ID for logging.
    """
    tid = trace_id or ""
    current_year = datetime.now().year

    if full_history:
        years_to_sync = list(range(FIRST_YEAR, current_year + 1))
    elif years:
        years_to_sync = years
    else:
        years_to_sync = [current_year]

    tracer.step(tid, "ipe_sync", f"Starting IPE sync for years: {years_to_sync}")

    conn = connect_ipe(read_only=False)
    _ensure_schema(conn)

    results = {"synced": [], "skipped": [], "errors": []}
    total_rows = 0

    for year in years_to_sync:
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE year=?", (year,),
            ).fetchone()
            if existing:
                results["skipped"].append(year)
                continue

        url = URL_PATTERN.format(year=year)
        tracer.step(tid, "ipe_sync", f"Downloading IPE {year}: {url}")

        try:
            raw = _download_zip(url)
            if not raw:
                results["errors"].append({"year": year, "error": "Download failed (empty response)"})
                continue

            row_count = _parse_and_store(conn, raw, year)
            total_rows += row_count

            conn.execute(
                "INSERT OR REPLACE INTO sync_state (year, synced_at, rows_added, duration_s) "
                "VALUES (?, ?, ?, ?)",
                (year, datetime.now().isoformat(), row_count, 0),
            )
            conn.commit()

            results["synced"].append({"year": year, "rows": row_count})
            tracer.step(tid, "ipe_sync", f"IPE {year}: {row_count} rows stored")

        except Exception as e:
            results["errors"].append({"year": year, "error": str(e)})
            tracer.warning(tid, "ipe_sync", f"IPE {year} failed: {e}")

    conn.close()

    return {
        "status": "ok" if not results["errors"] else "partial",
        "form": "IPE",
        "years_synced": results["synced"],
        "years_skipped": results["skipped"],
        "errors": results["errors"],
        "total_rows": total_rows,
    }


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _download_zip(url: str, timeout: int = 120) -> bytes:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


def _parse_and_store(conn: sqlite3.Connection, raw: bytes, year: int) -> int:
    """Parse the IPE ZIP (single CSV) and store all rows."""
    count = 0

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        # Find the data CSV (skip meta/dicionario)
        csv_entries = [
            n for n in zf.namelist()
            if n.lower().endswith(".csv")
            and "meta_" not in n.lower()
            and "dicion" not in n.lower()
        ]
        if not csv_entries:
            return 0

        for entry_name in csv_entries:
            raw_csv = zf.read(entry_name)
            # Try multiple encodings
            text = None
            for enc in ("utf-8-sig", "utf-8", CSV_ENCODING, "cp1252"):
                try:
                    text = raw_csv.decode(enc)
                    break
                except (UnicodeDecodeError, ValueError):
                    continue
            if not text:
                text = raw_csv.decode(CSV_ENCODING, errors="replace")

            reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
            if not reader.fieldnames:
                continue

            for row in reader:
                count += _store_row(conn, row, year)

    conn.commit()
    return count


def _store_row(conn: sqlite3.Connection, csv_row: dict, year: int) -> int:
    """Store a single IPE event row. Returns 1 if stored, 0 if skipped."""
    protocolo = (csv_row.get("Protocolo_Entrega") or "").strip()
    if not protocolo:
        return 0

    conn.execute(
        """INSERT OR REPLACE INTO eventos
           (cnpj, cd_cvm, nome, data_entrega, data_referencia,
            categoria, tipo, especie, assunto, tipo_apresentacao,
            versao, protocolo, link_download, ano_origem)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cnpj_digits(csv_row.get("CNPJ_Companhia", "")),
            (csv_row.get("Codigo_CVM") or "").strip(),
            (csv_row.get("Nome_Companhia") or "").strip(),
            (csv_row.get("Data_Entrega") or "").strip(),
            (csv_row.get("Data_Referencia") or "").strip(),
            (csv_row.get("Categoria") or "").strip(),
            (csv_row.get("Tipo") or "").strip(),
            (csv_row.get("Especie") or "").strip(),
            (csv_row.get("Assunto") or "").strip(),
            (csv_row.get("Tipo_Apresentacao") or "").strip(),
            int(csv_row.get("Versao", "1") or 1),
            protocolo,
            (csv_row.get("Link_Download") or "").strip(),
            year,
        ),
    )
    return 1
