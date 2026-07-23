"""data_sources/cvm/fre/sync_engine.py -- Download FRE ZIPs and populate fre.db.

FRE = Formulário de Referência (annual reference form).
Unlike DFP/ITR (financial statements), FRE is corporate governance +
ownership + compensation data. No meses/flow/snapshot concept.

The FRE ZIP contains 50+ CSVs. We import only the 5 most analytically useful:
  1. documentos (filing index)
  2. posicao_acionaria (shareholder composition)
  3. distribuicao_capital (free float)
  4. remuneracao_orgao (executive compensation)
  5. capital_social (stock capital + share counts)

DEDUP: Uses ID_DOC as primary key (globally unique CVM filing ID).
Re-syncing is idempotent — same doc always maps to same row.
Section tables use UNIQUE constraints on natural keys.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from core.tracer import tracer
from data_sources.cvm._db import connect_fre, fre_db_path, cnpj_digits
from data_sources.cvm.fre.catalog import (
    URL_PATTERN, FIRST_YEAR, CSV_ENCODING, CSV_DELIMITER, SCHEMA_SQL, FRE_TABLES,
)


def sync(
    years: list[int] | None = None,
    full_history: bool = False,
    force: bool = False,
    trace_id: str = "",
) -> dict:
    """Download FRE ZIPs and populate fre.db.

    Args:
        years: Specific years to sync. Default: current year.
        full_history: Sync all years from FIRST_YEAR (2010) to current.
        force: Re-download even if already synced.
        trace_id: Tracer ID for logging.

    Returns:
        Dict with sync status, years synced, row counts per table.
    """
    tid = trace_id or ""
    current_year = datetime.now().year

    if full_history:
        years_to_sync = list(range(FIRST_YEAR, current_year + 1))
    elif years:
        years_to_sync = years
    else:
        years_to_sync = [current_year]

    tracer.step(tid, "fre_sync", f"Starting FRE sync for years: {years_to_sync}")

    conn = connect_fre(read_only=False)
    _ensure_schema(conn)

    results = {"synced": [], "skipped": [], "errors": []}
    total_all = 0

    for year in years_to_sync:
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE year=?", (year,),
            ).fetchone()
            if existing:
                results["skipped"].append(year)
                continue

        url = URL_PATTERN.format(year=year)
        tracer.step(tid, "fre_sync", f"Downloading FRE {year}: {url}")

        try:
            raw = _download_zip(url)
            if not raw:
                results["errors"].append({"year": year, "error": "Download failed (empty response)"})
                continue

            counts = _parse_and_store(conn, raw, year, tid)
            total_all += sum(counts.values())

            duration = 0  # tracked externally if needed
            conn.execute(
                "INSERT OR REPLACE INTO sync_state "
                "(year, synced_at, rows_documentos, rows_posicao, rows_distrib, "
                "rows_remuneracao, rows_capital, duration_s) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (year, datetime.now().isoformat(),
                 counts.get("documentos", 0), counts.get("posicao_acionaria", 0),
                 counts.get("distribuicao_capital", 0), counts.get("remuneracao_orgao", 0),
                 counts.get("capital_social", 0), duration),
            )
            conn.commit()

            results["synced"].append({"year": year, "rows": counts})
            tracer.step(tid, "fre_sync", f"FRE {year}: {counts}")

        except Exception as e:
            results["errors"].append({"year": year, "error": str(e)})
            tracer.warning(tid, "fre_sync", f"FRE {year} failed: {e}")

    conn.close()

    return {
        "status": "ok" if not results["errors"] else "partial",
        "form": "FRE",
        "years_synced": results["synced"],
        "years_skipped": results["skipped"],
        "errors": results["errors"],
        "total_rows": total_all,
    }


# ── Schema ────────────────────────────────────────────────────────────────────

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create FRE tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ── Download ──────────────────────────────────────────────────────────────────

def _download_zip(url: str, timeout: int = 120) -> bytes:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _read_csv_from_zip(zf: zipfile.ZipFile, name_fragment: str) -> list[dict]:
    """Find a CSV in the ZIP whose name contains `name_fragment` and parse it."""
    for info in zf.infolist():
        if not info.filename.endswith(".csv"):
            continue
        if name_fragment in info.filename.lower():
            raw = zf.read(info.filename)
            text = raw.decode(CSV_ENCODING, errors="replace")
            reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
            return list(reader)
    return []


def _safe_float(val: str) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val: str) -> int | None:
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, TypeError):
        return None


# ── Parse + store ─────────────────────────────────────────────────────────────

def _parse_and_store(conn: sqlite3.Connection, raw: bytes, year: int, tid: str) -> dict:
    """Parse the FRE ZIP and store all 5 tables. Returns row counts."""
    counts = {}

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        # 1. Documentos (filing index)
        rows = _read_csv_from_zip(zf, f"fre_cia_aberta_{year}.csv")
        if not rows:
            # Try without year suffix (some ZIPs name differently)
            rows = _read_csv_from_zip(zf, "fre_cia_aberta_")
        counts["documentos"] = _store_documentos(conn, rows, year)

        # 2. Posição acionária
        rows = _read_csv_from_zip(zf, "posicao_acionaria")
        counts["posicao_acionaria"] = _store_posicao_acionaria(conn, rows)

        # 3. Distribuição capital
        rows = _read_csv_from_zip(zf, "distribuicao_capital")
        counts["distribuicao_capital"] = _store_distribuicao_capital(conn, rows)

        # 4. Remuneração
        rows = _read_csv_from_zip(zf, "remuneracao_total_orgao")
        counts["remuneracao_orgao"] = _store_remuneracao_orgao(conn, rows)

        # 5. Capital social
        rows = _read_csv_from_zip(zf, "capital_social")
        counts["capital_social"] = _store_capital_social(conn, rows)

    conn.commit()
    return counts


def _store_documentos(conn: sqlite3.Connection, rows: list[dict], year: int) -> int:
    count = 0
    for r in rows:
        id_doc = _safe_int(r.get("ID_DOC", ""))
        if not id_doc:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO documentos
               (id_doc, cnpj, cd_cvm, nome, categ_doc, dt_receb, dt_refer,
                versao, link_doc, ano_origem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_doc,
                cnpj_digits(r.get("CNPJ_CIA", "")),
                (r.get("CD_CVM") or "").strip(),
                (r.get("DENOM_CIA") or "").strip(),
                (r.get("CATEG_DOC") or "").strip(),
                (r.get("DT_RECEB") or "").strip(),
                (r.get("DT_REFER") or "").strip(),
                _safe_int(r.get("VERSAO", "1")) or 1,
                (r.get("LINK_DOC") or "").strip(),
                year,
            ),
        )
        count += 1
    return count


def _store_posicao_acionaria(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for r in rows:
        cnpj = cnpj_digits(r.get("CNPJ_Companhia", ""))
        id_doc = _safe_int(r.get("ID_Documento", ""))
        if not cnpj or not id_doc:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO posicao_acionaria
               (cnpj, id_documento, data_referencia, versao, nome_companhia,
                acionista, cpf_cnpj_acionista, tipo_pessoa, nacionalidade,
                acionista_controlador, participante_acordo_acionistas,
                pct_on, pct_pn, pct_total, qtd_on, qtd_pn, qtd_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cnpj, id_doc,
                (r.get("Data_Referencia") or "").strip(),
                _safe_int(r.get("Versao", "1")) or 1,
                (r.get("Nome_Companhia") or "").strip(),
                (r.get("Acionista") or "").strip(),
                cnpj_digits(r.get("CPF_CNPJ_Acionista", "")),
                (r.get("Tipo_Pessoa") or "").strip(),
                (r.get("Nacionalidade") or "").strip(),
                (r.get("Acionista_Controlador") or "").strip(),
                (r.get("Participante_Acordo_Acionistas") or "").strip(),
                _safe_float(r.get("Pct_ON", "")),
                _safe_float(r.get("Pct_PN", "")),
                _safe_float(r.get("Pct_Total", "")),
                _safe_int(r.get("Qtd_ON", "")),
                _safe_int(r.get("Qtd_PN", "")),
                _safe_int(r.get("Qtd_Total", "")),
            ),
        )
        count += 1
    return count


def _store_distribuicao_capital(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for r in rows:
        cnpj = cnpj_digits(r.get("CNPJ_Companhia", ""))
        id_doc = _safe_int(r.get("ID_Documento", ""))
        if not cnpj or not id_doc:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO distribuicao_capital
               (cnpj, id_documento, data_referencia, versao, nome_companhia,
                pct_on_circulacao, pct_pn_circulacao, pct_total_circulacao,
                qtd_on_circulacao, qtd_pn_circulacao, qtd_total_circulacao,
                qtd_acionistas_pf, qtd_acionistas_pj, qtd_acionistas_inst,
                data_ultima_assembleia)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cnpj, id_doc,
                (r.get("Data_Referencia") or "").strip(),
                _safe_int(r.get("Versao", "1")) or 1,
                (r.get("Nome_Companhia") or "").strip(),
                _safe_float(r.get("Pct_ON_Circulacao", "")),
                _safe_float(r.get("Pct_PN_Circulacao", "")),
                _safe_float(r.get("Pct_Total_Circulacao", "")),
                _safe_int(r.get("Qtd_ON_Circulacao", "")),
                _safe_int(r.get("Qtd_PN_Circulacao", "")),
                _safe_int(r.get("Qtd_Total_Circulacao", "")),
                _safe_int(r.get("Qtd_Acionistas_PF", "")),
                _safe_int(r.get("Qtd_Acionistas_PJ", "")),
                _safe_int(r.get("Qtd_Acionistas_Institucionais", "")),
                (r.get("Data_Ultima_Assembleia") or "").strip(),
            ),
        )
        count += 1
    return count


def _store_remuneracao_orgao(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for r in rows:
        cnpj = cnpj_digits(r.get("CNPJ_Companhia", ""))
        id_doc = _safe_int(r.get("ID_Documento", ""))
        if not cnpj or not id_doc:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO remuneracao_orgao
               (cnpj, id_documento, data_referencia, versao, nome_companhia,
                orgao, dt_ini_exercicio, dt_fim_exercicio,
                num_membros, num_membros_remunerados,
                salario, beneficios, bonus, participacao_resultados,
                baseada_acoes, total_remuneracao, total_remuneracao_orgao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cnpj, id_doc,
                (r.get("Data_Referencia") or "").strip(),
                _safe_int(r.get("Versao", "1")) or 1,
                (r.get("Nome_Companhia") or "").strip(),
                (r.get("Orgao") or "").strip(),
                (r.get("Data_Inicio_Exercicio") or "").strip(),
                (r.get("Data_Fim_Exercicio") or "").strip(),
                _safe_float(r.get("Numero_Membros", "")),
                _safe_float(r.get("Numero_Membros_Remunerados", "")),
                _safe_float(r.get("Salario", "")),
                _safe_float(r.get("Beneficios_Diretos_Indiretos", "")),
                _safe_float(r.get("Bonus", "")),
                _safe_float(r.get("Participacao_Resultados", "")),
                _safe_float(r.get("Baseada_Acoes", "")),
                _safe_float(r.get("Total_Remuneracao", "")),
                _safe_float(r.get("Total_Remuneracao_Orgao", "")),
            ),
        )
        count += 1
    return count


def _store_capital_social(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for r in rows:
        cnpj = cnpj_digits(r.get("CNPJ_Companhia", ""))
        id_doc = _safe_int(r.get("ID_Documento", ""))
        if not cnpj or not id_doc:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO capital_social
               (cnpj, id_documento, data_referencia, versao, nome_companhia,
                tipo_capital, valor_capital,
                qtd_acoes_on, qtd_acoes_pn, qtd_acoes_total, data_aprovacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cnpj, id_doc,
                (r.get("Data_Referencia") or "").strip(),
                _safe_int(r.get("Versao", "1")) or 1,
                (r.get("Nome_Companhia") or "").strip(),
                (r.get("Tipo_Capital") or "").strip(),
                _safe_float(r.get("Valor_Capital", "")),
                _safe_int(r.get("Qtd_Acoes_ON", "")),
                _safe_int(r.get("Qtd_Acoes_PN", "")),
                _safe_int(r.get("Qtd_Acoes_Total", "")),
                (r.get("Data_Aprovacao") or "").strip(),
            ),
        )
        count += 1
    return count
