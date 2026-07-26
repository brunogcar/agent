"""data_sources/cvm/vlmo/sync_engine.py -- Download + parse VLMO ZIPs from CVM.

Downloads annual ZIP files, extracts CSVs, parses into SQLite.
Pattern follows DFP/ITR/FRE sync engines.

Supports:
  sync(year=2025)           -- sync single year
  sync(full_history=True)   -- sync all years from 2010 to current
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from typing import Any

from data_sources.cvm._db import connect_vlmo, vlmo_db_path
from data_sources.cvm.vlmo.catalog import ensure_schema


VLMO_BASE_URL = "http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS"

# CVM started VLMO filings in 2017 (first full year of data)
VLMO_FIRST_YEAR = 2017


def _download_zip(url: str) -> bytes:
    """Download a ZIP file from CVM. Returns bytes."""
    import httpx
    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def sync(
    year: int = 0,
    force: bool = False,
    full_history: bool = False,
) -> dict:
    """Download + parse VLMO data from CVM into vlmo.db.

    Args:
        year: Year to sync (e.g., 2025). 0 = current year.
        force: Re-download even if already synced today.
        full_history: Sync all years from VLMO_FIRST_YEAR to current.

    Returns:
        {status, years_synced, years_skipped, total_rows, ...}
    """
    current_year = datetime.now().year

    if full_history:
        return _sync_full_history(force=force)

    if year == 0:
        year = current_year

    return _sync_single_year(year, force=force)


def _sync_full_history(force: bool = False) -> dict:
    """Sync all years from VLMO_FIRST_YEAR to current."""
    current_year = datetime.now().year
    years_synced = []
    years_skipped = []
    total_rows = 0
    errors = []

    for yr in range(VLMO_FIRST_YEAR, current_year + 1):
        result = _sync_single_year(yr, force=force)
        if result.get("status") == "ok":
            years_synced.append(yr)
            total_rows += result.get("movement_rows", 0)
        elif result.get("status") == "skipped":
            years_skipped.append(yr)
        else:
            errors.append(f"{yr}: {result.get('error', '')}")

    return {
        "status": "ok",
        "years_synced": years_synced,
        "years_skipped": years_skipped,
        "total_movement_rows": total_rows,
        "errors": errors,
    }


def _sync_single_year(year: int, force: bool = False) -> dict:
    """Download + parse a single year of VLMO data."""
    # Check if already synced today
    if not force:
        try:
            conn = connect_vlmo(read_only=True)
            row = conn.execute(
                "SELECT synced_at FROM sync_state WHERE year=? ORDER BY rowid DESC LIMIT 1",
                (year,),
            ).fetchone()
            conn.close()
            if row and row["synced_at"]:
                synced_date = str(row["synced_at"])[:10]
                today = datetime.now().strftime("%Y-%m-%d")
                if synced_date == today:
                    return {"status": "skipped", "reason": "already synced today",
                            "year": year, "synced_at": row["synced_at"]}
        except FileNotFoundError:
            pass

    # Download ZIP
    url = f"{VLMO_BASE_URL}/vlmo_cia_aberta_{year}.zip"
    print(f"[vlmo] Downloading {url}...")
    try:
        zip_data = _download_zip(url)
    except Exception as e:
        return {"status": "error", "error": f"Download failed: {e}", "url": url}

    if not zip_data:
        return {"status": "error", "error": "Empty download", "url": url}

    # Parse ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_data))
    except zipfile.BadZipFile as e:
        return {"status": "error", "error": f"Bad ZIP: {e}", "url": url}

    # Find CSV files — CVM names them with year suffix:
    #   vlmo_cia_aberta_YYYY.csv      (documents)
    #   vlmo_cia_aberta_con_YYYY.csv  (movements)
    # Match by prefix, not exact name.
    doc_file = None
    mov_file = None
    for name in zf.namelist():
        lower = name.lower()
        if lower.endswith(".csv"):
            if "vlmo_cia_aberta_con" in lower:
                mov_file = name
            elif "vlmo_cia_aberta" in lower:
                doc_file = name

    if not mov_file:
        return {"status": "error",
                "error": f"movements CSV not found in ZIP. Files: {zf.namelist()}"}

    # Parse + insert
    conn = connect_vlmo(read_only=False)
    try:
        ensure_schema(conn)

        # Delete existing data for this year before re-inserting
        # We filter by Data_Referencia year (VLMO has a Data_Referencia column)
        year_prefix = str(year)
        conn.execute(
            "DELETE FROM vlmo_movements WHERE substr(Data_Referencia, 1, 4) = ?",
            (year_prefix,),
        )
        conn.execute(
            "DELETE FROM vlmo_documents WHERE substr(Data_Referencia, 1, 4) = ?",
            (year_prefix,),
        )

        doc_rows = 0
        mov_rows = 0

        # Parse documents CSV (if present)
        if doc_file:
            doc_rows = _parse_and_insert_csv(
                conn, zf, doc_file, "vlmo_documents",
                ["Categoria", "CNPJ_Companhia", "Codigo_CVM", "Data_Entrega",
                 "Data_Referencia", "Link_Download", "Nome_Companhia",
                 "Protocolo_Entrega", "Tipo", "Tipo_Apresentacao", "Versao",
                 "Motivo_Reapresentacao"]
            )

        # Parse movements CSV (the valuable one)
        mov_rows = _parse_and_insert_csv(
            conn, zf, mov_file, "vlmo_movements",
            ["CNPJ_Companhia", "Data_Referencia", "Nome_Companhia",
             "Preco_Unitario", "Tipo_Ativo", "Versao",
             "Descricao_Movimentacao", "Intermediario", "Tipo_Cargo",
             "Empresa", "Data_Movimentacao", "Tipo_Movimentacao",
             "Quantidade", "Caracteristica_Valor_Mobiliario",
             "Volume", "Tipo_Empresa", "Tipo_Operacao"]
        )

        # Record sync state
        conn.execute(
            "INSERT INTO sync_state (synced_at, year, rows_synced) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), year, mov_rows),
        )
        conn.commit()

        return {
            "status": "ok",
            "year": year,
            "document_rows": doc_rows,
            "movement_rows": mov_rows,
            "total_rows": doc_rows + mov_rows,
            "synced_at": datetime.now().isoformat(),
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def _parse_and_insert_csv(
    conn, zf, csv_name: str, table: str, columns: list[str]
) -> int:
    """Parse a CSV from the ZIP and insert into the given table.

    Returns: number of rows inserted.
    """
    data = zf.read(csv_name)
    text = data.decode("latin-1")  # CVM uses latin-1 encoding

    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    # Build INSERT statement
    placeholders = ",".join(["?"] * len(columns))
    col_names = ",".join(columns)
    insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

    batch = []
    batch_size = 5000
    rows_inserted = 0

    for row in reader:
        values = []
        for col in columns:
            val = row.get(col, "")
            if val == "" or val is None:
                values.append(None)
            else:
                if col in ("Preco_Unitario", "Quantidade", "Volume"):
                    try:
                        val = val.replace(",", ".")
                        values.append(float(val))
                    except (ValueError, AttributeError):
                        values.append(None)
                elif col in ("Versao",):
                    try:
                        values.append(int(val))
                    except (ValueError, TypeError):
                        values.append(None)
                else:
                    values.append(val)
        batch.append(values)

        if len(batch) >= batch_size:
            conn.executemany(insert_sql, batch)
            rows_inserted += len(batch)
            batch = []

    if batch:
        conn.executemany(insert_sql, batch)
        rows_inserted += len(batch)

    print(f"[vlmo] {table}: {rows_inserted} rows inserted")
    return rows_inserted
