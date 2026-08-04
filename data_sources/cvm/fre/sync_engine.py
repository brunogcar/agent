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
import sys
import time
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
    verbose: bool = True,
) -> dict:
    """Download FRE ZIPs and populate fre.db.

    Args:
        years: Specific years to sync. Default: current year.
        full_history: Sync all years from FIRST_YEAR (2010) to current.
        force: Re-download even if already synced.
        trace_id: Tracer ID for logging.
        verbose: Print progress to stderr.

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

    def _log(msg: str) -> None:
        if verbose:
            print(f"[fre] {msg}", file=sys.stderr, flush=True)

    _log(f"Starting FRE sync — {len(years_to_sync)} year(s): {years_to_sync[0]}..{years_to_sync[-1]}")
    tracer.step(tid, "fre_sync", f"Starting FRE sync for years: {years_to_sync}")

    conn = connect_fre(read_only=False)
    _ensure_schema(conn)

    results = {"synced": [], "skipped": [], "errors": []}
    total_all = 0
    sync_start = time.time()

    for idx, year in enumerate(years_to_sync, 1):
        _log(f"[{idx}/{len(years_to_sync)}] Year {year} ...")
        if not force:
            existing = conn.execute(
                "SELECT * FROM sync_state WHERE year=?", (year,),
            ).fetchone()
            if existing:
                _log(f"  skip (already synced, use force=True to re-download)")
                results["skipped"].append(year)
                continue

        url = URL_PATTERN.format(year=year)
        _log(f"  downloading {url}")
        tracer.step(tid, "fre_sync", f"Downloading FRE {year}: {url}")

        try:
            t0 = time.time()
            raw = _download_zip(url)
            dl_secs = time.time() - t0
            if not raw:
                _log(f"  FAILED: empty response")
                results["errors"].append({"year": year, "error": "Download failed (empty response)"})
                continue
            _log(f"  downloaded {len(raw) / 1024 / 1024:.1f} MB in {dl_secs:.1f}s")

            t1 = time.time()
            counts = _parse_and_store(conn, raw, year, tid)
            parse_secs = time.time() - t1
            total_all += sum(counts.values())
            _log(f"  parsed + stored {sum(counts.values()):,} rows in {parse_secs:.1f}s")

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
            _log(f"  FAILED: {e}")
            results["errors"].append({"year": year, "error": str(e)})
            tracer.warning(tid, "fre_sync", f"FRE {year} failed: {e}")

    conn.close()
    elapsed = time.time() - sync_start
    _log(f"Done in {elapsed:.1f}s — {total_all:,} total rows, {len(results['errors'])} errors")

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

def _read_csv_from_zip(zf: zipfile.ZipFile, name_fragment: str, year: int | None = None) -> list[dict]:
    """Find a CSV in the ZIP matching `name_fragment` and parse it.

    [v1.2] Fixed: was loose substring match (`fragment in filename`) which could
    match sibling files (e.g. "posicao_acionaria" matched BOTH
    posicao_acionaria_2026.csv AND posicao_acionaria_classe_acao_2026.csv —
    whichever came first in the zip listing). Now uses exact match against
    `fre_cia_aberta_{fragment}_{year}.csv` when year is provided, with a
    fallback that explicitly excludes suffixed variants (_classe_acao,
    _aumento, _desdobramento, _reducao, etc.).
    """
    # Build the list of files to check, sorted for deterministic order.
    csv_files = [info for info in zf.infolist() if info.filename.lower().endswith(".csv")]

    # If year is provided, try exact match first: fre_cia_aberta_{fragment}_{year}.csv
    # (or fre_cia_aberta_{year}.csv when fragment is empty — for documentos)
    if year is not None:
        if name_fragment:
            exact_name = f"fre_cia_aberta_{name_fragment}_{year}.csv".lower()
        else:
            exact_name = f"fre_cia_aberta_{year}.csv".lower()
        for info in csv_files:
            if info.filename.lower() == exact_name:
                raw = zf.read(info.filename)
                text = raw.decode(CSV_ENCODING, errors="replace")
                reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
                return list(reader)

    # Fallback: match files that START with fre_cia_aberta_{fragment}_ AND end
    # with _{year}.csv (or just .csv if year is None). This excludes siblings
    # like _classe_acao, _aumento, etc. because those have an extra segment
    # between the fragment and the year.
    if name_fragment:
        prefix = f"fre_cia_aberta_{name_fragment}_".lower()
    else:
        prefix = "fre_cia_aberta_".lower()
    suffix = f"_{year}.csv" if year is not None else ".csv"

    for info in csv_files:
        lower = info.filename.lower()
        if lower.startswith(prefix) and lower.endswith(suffix):
            # Exclude suffixed variants: the part between prefix and suffix
            # should be JUST the year (4 digits), not a sub-table name.
            middle = lower[len(prefix):-len(suffix)]
            if year is not None:
                # When year is provided, middle should be empty (exact match
                # already tried above) — this handles edge cases.
                if middle == "":
                    raw = zf.read(info.filename)
                    text = raw.decode(CSV_ENCODING, errors="replace")
                    reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
                    return list(reader)
            else:
                # No year: accept only if middle is a 4-digit year (not a
                # sub-table name like "classe_acao").
                if middle.isdigit() and len(middle) == 4:
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
        # 1. Documentos (filing index) — the documentos file is just
        # fre_cia_aberta_{year}.csv (no table-name fragment in the middle).
        rows = _read_csv_from_zip(zf, "", year=year)
        if not rows:
            # Fallback: try without year (some older ZIPs name differently)
            rows = _read_csv_from_zip(zf, "")
        counts["documentos"] = _store_documentos(conn, rows, year)

        # 2. Posição acionária — excludes posicao_acionaria_classe_acao sibling
        rows = _read_csv_from_zip(zf, "posicao_acionaria", year=year)
        counts["posicao_acionaria"] = _store_posicao_acionaria(conn, rows)

        # 3. Distribuição capital — excludes distribuicao_capital_classe_acao sibling
        rows = _read_csv_from_zip(zf, "distribuicao_capital", year=year)
        counts["distribuicao_capital"] = _store_distribuicao_capital(conn, rows)

        # 4. Remuneração — excludes remuneracao_total_orgao siblings
        rows = _read_csv_from_zip(zf, "remuneracao_total_orgao", year=year)
        counts["remuneracao_orgao"] = _store_remuneracao_orgao(conn, rows)

        # 5. Capital social — excludes capital_social_aumento/desdobramento/reducao siblings
        rows = _read_csv_from_zip(zf, "capital_social", year=year)
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
                # [v1.1] Fixed — CVM uses Tipo_Pessoa_Acionista.
                (r.get("Tipo_Pessoa_Acionista") or "").strip(),
                (r.get("Nacionalidade") or "").strip(),
                (r.get("Acionista_Controlador") or "").strip(),
                (r.get("Participante_Acordo_Acionistas") or "").strip(),
                # [v1.1] Fixed column names — CVM FRE CSV uses full names
                # (Percentual_Acao_Ordinaria_Circulacao, not Pct_ON).
                # The old abbreviated names caused all pct/qtd values to be
                # stored as NULL (r.get returned "" -> _safe_float -> None).
                _safe_float(r.get("Percentual_Acao_Ordinaria_Circulacao", "")),
                _safe_float(r.get("Percentual_Acao_Preferencial_Circulacao", "")),
                _safe_float(r.get("Percentual_Total_Acoes_Circulacao", "")),
                _safe_int(r.get("Quantidade_Acao_Ordinaria_Circulacao", "")),
                _safe_int(r.get("Quantidade_Acao_Preferencial_Circulacao", "")),
                _safe_int(r.get("Quantidade_Total_Acoes_Circulacao", "")),
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
                # [v1.1] Fixed column names — CVM FRE CSV uses full names
                # (Percentual_Acoes_Ordinarias_Circulacao, not Pct_ON_Circulacao).
                _safe_float(r.get("Percentual_Acoes_Ordinarias_Circulacao", "")),
                _safe_float(r.get("Percentual_Acoes_Preferenciais_Circulacao", "")),
                _safe_float(r.get("Percentual_Total_Acoes_Circulacao", "")),
                _safe_int(r.get("Quantidade_Acoes_Ordinarias_Circulacao", "")),
                _safe_int(r.get("Quantidade_Acoes_Preferenciais_Circulacao", "")),
                _safe_int(r.get("Quantidade_Total_Acoes_Circulacao", "")),
                _safe_int(r.get("Quantidade_Acionistas_PF", "")),
                _safe_int(r.get("Quantidade_Acionistas_PJ", "")),
                _safe_int(r.get("Quantidade_Acionistas_Investidores_Institucionais", "")),
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
                # [v1.1] Fixed column names — CVM uses Orgao_Administracao,
                # Data_Inicio_Exercicio_Social, Data_Fim_Exercicio_Social.
                (r.get("Orgao_Administracao") or "").strip(),
                (r.get("Data_Inicio_Exercicio_Social") or "").strip(),
                (r.get("Data_Fim_Exercicio_Social") or "").strip(),
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
                # [v1.1] Fixed column names — CVM uses Quantidade_Acoes_*,
                # Data_Autorizacao_Aprovacao.
                _safe_int(r.get("Quantidade_Acoes_Ordinarias", "")),
                _safe_int(r.get("Quantidade_Acoes_Preferenciais", "")),
                _safe_int(r.get("Quantidade_Total_Acoes", "")),
                (r.get("Data_Autorizacao_Aprovacao") or "").strip(),
            ),
        )
        count += 1
    return count
