"""data_sources/cvm/fca/sync_engine.py -- Download + parse FCA ZIPs from CVM.

Downloads annual ZIP files, extracts CSVs (3 of 9 — skips contact info),
parses into SQLite. Pattern follows VLMO/CGVN sync engines.

Supports:
  sync(year=2025)           -- sync single year
  sync(full_history=True)   -- sync all years from FCA_FIRST_YEAR to current
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from typing import Any

from data_sources.cvm.fca.catalog import connect, ensure_schema, db_path


FCA_BASE_URL = "http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS"

# CVM started FCA filings in 2018
FCA_FIRST_YEAR = 2018


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
    """Download + parse FCA data from CVM into fca.db.

    Args:
        year: Year to sync (e.g., 2025). 0 = current year.
        force: Re-download even if already synced today.
        full_history: Sync all years from FCA_FIRST_YEAR to current.

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
    """Sync all years from FCA_FIRST_YEAR to current."""
    current_year = datetime.now().year
    years_synced = []
    years_skipped = []
    total_rows = 0
    errors = []

    for yr in range(FCA_FIRST_YEAR, current_year + 1):
        result = _sync_single_year(yr, force=force)
        if result.get("status") == "ok":
            years_synced.append(yr)
            total_rows += result.get("total_rows", 0)
        elif result.get("status") == "skipped":
            years_skipped.append(yr)
        else:
            errors.append(f"{yr}: {result.get('error', '')}")

    return {
        "status": "ok",
        "years_synced": years_synced,
        "years_skipped": years_skipped,
        "total_rows": total_rows,
        "errors": errors,
    }


def _sync_single_year(year: int, force: bool = False) -> dict:
    """Download + parse a single year of FCA data."""
    # Check if already synced today
    if not force:
        try:
            conn = connect(read_only=True)
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
    url = f"{FCA_BASE_URL}/fca_cia_aberta_{year}.zip"
    print(f"[fca] Downloading {url}...")
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
    #   fca_cia_aberta_geral_YYYY.csv
    #   fca_cia_aberta_valor_mobiliario_YYYY.csv
    #   fca_cia_aberta_pais_estrangeiro_negociacao_YYYY.csv
    # Match by prefix, not exact name.
    geral_file = None
    vm_file = None
    pe_file = None
    for name in zf.namelist():
        lower = name.lower()
        if lower.endswith(".csv"):
            if "fca_cia_aberta_geral" in lower:
                geral_file = name
            elif "fca_cia_aberta_valor_mobiliario" in lower:
                vm_file = name
            elif "fca_cia_aberta_pais_estrangeiro" in lower:
                pe_file = name

    if not vm_file:
        return {"status": "error",
                "error": f"valor_mobiliario CSV not found in ZIP. Files: {zf.namelist()}"}

    # Parse + insert
    conn = connect(read_only=False)
    try:
        ensure_schema(conn)

        # Delete existing data for this year before re-inserting
        year_prefix = str(year)
        conn.execute("DELETE FROM fca_geral WHERE substr(Data_Referencia, 1, 4) = ?", (year_prefix,))
        conn.execute("DELETE FROM fca_valor_mobiliario WHERE substr(Data_Referencia, 1, 4) = ?", (year_prefix,))
        conn.execute("DELETE FROM fca_pais_estrangeiro WHERE substr(Data_Referencia, 1, 4) = ?", (year_prefix,))

        geral_rows = 0
        vm_rows = 0
        pe_rows = 0

        # Parse geral CSV (if present)
        if geral_file:
            geral_rows = _parse_and_insert_csv(
                conn, zf, geral_file, "fca_geral",
                ["Categoria_Registro_CVM", "CNPJ_Companhia", "Codigo_CVM",
                 "Data_Alteracao_Exercicio_Social", "Data_Categoria_Registro_CVM",
                 "Data_Constituicao", "Data_Especie_Controle_Acionario",
                 "Data_Nome_Empresarial", "Data_Referencia", "Data_Registro_CVM",
                 "Data_Situacao_Emissor", "Data_Situacao_Registro_CVM",
                 "Descricao_Atividade", "Dia_Encerramento_Exercicio_Social",
                 "Especie_Controle_Acionario", "ID_Documento",
                 "Mes_Encerramento_Exercicio_Social", "Nome_Empresarial",
                 "Nome_Empresarial_Anterior", "Pagina_Web",
                 "Pais_Custodia_Valores_Mobiliarios", "Pais_Origem",
                 "Setor_Atividade", "Situacao_Emissor", "Situacao_Registro_CVM",
                 "Versao"]
            )

        # Parse valor_mobiliario CSV (the valuable one — ticker -> CNPJ)
        vm_rows = _parse_and_insert_csv(
            conn, zf, vm_file, "fca_valor_mobiliario",
            ["CNPJ_Companhia", "Codigo_Negociacao", "Classe_Acao_Preferencial",
             "Composicao_BDR_Unit", "Data_Fim_Listagem", "Data_Fim_Negociacao",
             "Data_Inicio_Listagem", "Data_Inicio_Negociacao", "Data_Referencia",
             "Entidade_Administradora", "ID_Documento", "Mercado",
             "Nome_Empresarial", "Segmento", "Sigla_Classe_Acao_Preferencial",
             "Sigla_Entidade_Administradora", "Valor_Mobiliario", "Versao"]
        )

        # Parse pais_estrangeiro CSV (if present — foreign listings)
        if pe_file:
            pe_rows = _parse_and_insert_csv(
                conn, zf, pe_file, "fca_pais_estrangeiro",
                ["CNPJ_Companhia", "Data_Admissao_Negociacao", "Data_Referencia",
                 "ID_Documento", "Nome_Empresarial", "Pais", "Versao"]
            )

        # Record sync state
        total = geral_rows + vm_rows + pe_rows
        conn.execute(
            "INSERT INTO sync_state (synced_at, year, rows_synced) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), year, total),
        )
        conn.commit()

        return {
            "status": "ok",
            "year": year,
            "geral_rows": geral_rows,
            "valor_mobiliario_rows": vm_rows,
            "pais_estrangeiro_rows": pe_rows,
            "total_rows": total,
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
                if col in ("ID_Documento", "Versao",
                           "Dia_Encerramento_Exercicio_Social",
                           "Mes_Encerramento_Exercicio_Social"):
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

    print(f"[fca] {table}: {rows_inserted} rows inserted")
    return rows_inserted
