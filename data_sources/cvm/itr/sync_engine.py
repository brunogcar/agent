"""data_sources/cvm/itr/sync_engine.py -- Download ITR ZIPs and populate itr.db.

ITR = Informações Trimestrais (quarterly financial statements).
Same CSV format as DFP, same sync logic, different URL + DB.

Same fixes as DFP sync_engine.py:
  1. meses computed with rapinav2's inclusive formula
  2. meses=15 preserved
  3. empresas.ano = fiscal year (DT_FIM_EXERC[:4])
  4. ORDEM_EXERC filter (ÚLTIMO + PENÚLTIMO for 2009)
  5. VERSAO dedup
  6. data_ini_exerc stored
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
import zipfile
from datetime import datetime
from typing import Any

import requests

from core.tracer import tracer
from data_sources.cvm._db import connect_itr, itr_db_path
from data_sources.cvm._meses import compute_meses, should_keep_row, is_valid_meses
from data_sources.cvm.itr.catalog import (
    URL_PATTERN, FIRST_YEAR, CSV_ENCODING, CSV_DELIMITER,
)


def sync(
    years: list[int] | None = None,
    full_history: bool = False,
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download ITR ZIPs and populate itr.db.

    Args:
        years: Specific years to sync. Default: current year.
        full_history: Sync all years from FIRST_YEAR (2015) to current.
        force: Re-download even if already synced.
        trace_id: Tracer ID for logging.

    Returns:
        Dict with sync status, years synced, row counts.
    """
    tid = trace_id or ""
    current_year = datetime.now().year

    if full_history:
        years_to_sync = list(range(FIRST_YEAR, current_year + 1))
    elif years:
        years_to_sync = years
    else:
        years_to_sync = [current_year]

    tracer.step(tid, "itr_sync", f"Starting ITR sync for years: {years_to_sync}")

    conn = connect_itr(read_only=False)

    results = {"synced": [], "skipped": [], "errors": []}
    total_rows = 0

    for year in years_to_sync:
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE form='ITR' AND year=?",
                (year,),
            ).fetchone()
            if existing:
                results["skipped"].append(year)
                continue

        url = URL_PATTERN.format(year=year)
        tracer.step(tid, "itr_sync", f"Downloading ITR {year}: {url}")

        try:
            raw = _download_zip(url)
            if not raw:
                results["errors"].append({"year": year, "error": "Download failed (empty response)"})
                continue

            row_count = _parse_and_store(conn, raw, year, tid)
            total_rows += row_count

            conn.execute(
                "INSERT OR REPLACE INTO sync_state (form, year, synced_at, row_count, file_size) "
                "VALUES ('ITR', ?, ?, ?, ?)",
                (year, datetime.now().isoformat(), row_count, len(raw)),
            )
            conn.commit()

            results["synced"].append({"year": year, "rows": row_count})
            tracer.step(tid, "itr_sync", f"ITR {year}: {row_count} rows stored")

        except Exception as e:
            results["errors"].append({"year": year, "error": str(e)})
            tracer.warning(tid, "itr_sync", f"ITR {year} failed: {e}")

    conn.close()

    return {
        "status": "ok" if not results["errors"] else "partial",
        "form": "ITR",
        "years_synced": results["synced"],
        "years_skipped": results["skipped"],
        "errors": results["errors"],
        "total_rows": total_rows,
    }


def _download_zip(url: str, timeout: int = 120) -> bytes:
    """Download a ZIP file from CVM."""
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


def _parse_and_store(conn: sqlite3.Connection, raw: bytes, year: int, tid: str) -> int:
    """Parse an ITR ZIP and store all rows into the DB."""
    row_count = 0
    empresa_cache: dict[str, int] = {}
    versao_cache: dict[str, int] = {}

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".csv"):
                continue
            lower = info.filename.lower()
            if "meta_" in lower or "dicion" in lower:
                continue
            # [v1.0.1 P0] Skip DMPL files — 2D statement (COLUNA_DF) needs schema
            # support. rapinav2 also excludes DMPL for this reason.
            if "dmpl" in lower:
                continue

            raw_csv = zf.read(info.filename)
            text = raw_csv.decode(CSV_ENCODING, errors="replace")

            reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
            if not reader.fieldnames:
                continue

            for row in reader:
                row_count += _process_row(
                    conn, row, year, empresa_cache, versao_cache,
                )

    return row_count


def _process_row(
    conn: sqlite3.Connection,
    csv_row: dict[str, str],
    filing_year: int,
    empresa_cache: dict[str, int],
    versao_cache: dict[str, int],
) -> int:
    """Process a single CSV row. Returns 1 if stored, 0 if skipped."""
    cnpj = (csv_row.get("CNPJ_CIA") or "").strip()
    nome = (csv_row.get("DENOM_CIA") or "").strip()
    cd_cvm = (csv_row.get("CD_CVM") or "").strip()
    grupo = (csv_row.get("GRUPO_DFP") or "").strip()
    dt_ini = (csv_row.get("DT_INI_EXERC") or "").strip()
    dt_fim = (csv_row.get("DT_FIM_EXERC") or "").strip()
    codigo = (csv_row.get("CD_CONTA") or "").strip()
    descricao = (csv_row.get("DS_CONTA") or "").strip()
    valor_str = (csv_row.get("VL_CONTA") or "0").strip()
    ordem = (csv_row.get("ORDEM_EXERC") or "").strip()
    versao_str = (csv_row.get("VERSAO") or "1").strip()
    moeda = (csv_row.get("MOEDA") or "").strip()
    escala = (csv_row.get("ESCALA_MOEDA") or "").strip()
    st_conta_fixa = (csv_row.get("ST_CONTA_FIXA") or "").strip()

    if not cnpj or not dt_fim or not codigo:
        return 0

    # ano = fiscal year
    try:
        ano = int(dt_fim[:4])
    except (ValueError, IndexError):
        return 0

    # ORDEM_EXERC filter
    if not should_keep_row(ordem, dt_fim):
        return 0

    # Compute meses
    meses = compute_meses(dt_ini, dt_fim)
    if not is_valid_meses(meses):
        return 0

    # VERSAO dedup
    try:
        versao = int(versao_str)
    except ValueError:
        versao = 1

    cache_key = f"{cnpj}_{ano}"
    if cache_key in versao_cache and versao < versao_cache[cache_key]:
        return 0
    versao_cache[cache_key] = max(versao_cache.get(cache_key, 0), versao)

    # Consolidado
    consolidado = 1 if "CONSOLID" in grupo.upper() else 0

    # Valor
    try:
        valor = float(valor_str)
    except ValueError:
        valor = 0.0

    # Upsert empresa
    empresa_key = f"{cnpj}_{ano}"
    if empresa_key not in empresa_cache:
        conn.execute(
            "INSERT OR IGNORE INTO empresas (cnpj, nome, ano, cd_cvm) VALUES (?, ?, ?, ?)",
            (cnpj, nome, ano, cd_cvm),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM empresas WHERE cnpj=? AND ano=?", (cnpj, ano),
        ).fetchone()
        if row:
            empresa_cache[empresa_key] = row["id"]
        else:
            return 0
    empresa_id = empresa_cache[empresa_key]

    # Upsert conta
    conn.execute(
        """INSERT OR REPLACE INTO contas
           (id_empresa, codigo, descricao, grupo, consolidado,
            data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao,
            st_conta_fixa, valor, escala, moeda)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (empresa_id, codigo, descricao, grupo, consolidado,
         dt_ini, dt_fim, meses, ordem, versao,
         st_conta_fixa, valor, escala, moeda),
    )

    return 1
