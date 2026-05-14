"""
skills/cvm/cvm_api.py -- Query rapina.db for CVM financial statement data.

WHAT THIS DOES
--------------
Reads rapina.db (built by rapinav2) and returns financial data in four views
matching the four main sheets rapinav2 generates in Excel:

  completo_anual   -- all account codes, meses=12, consolidated
  completo_trim    -- all account codes, meses=3/6/9, consolidated
  resumo_anual     -- key metrics only, meses=12, consolidated
  resumo_trim      -- key metrics only, meses=3/6/9, consolidated

COMPANY LOOKUP
--------------
Company resolution order (first match wins):
  1. CNPJ exact match (formatted or numeric) -- most reliable
  2. Name exact match (case-insensitive)
  3. Name partial match (LIKE %query%)

CNPJ-YEAR ID PATTERN
---------------------
rapinav2 stores one empresas row per company per YEAR (id changes each year).
To query multiple years: collect all ids for a CNPJ, then query contas by
id_empresa IN (...). This is the correct pattern -- do NOT assume one company
has one stable id.

REAL VALUE CALCULATION
----------------------
contas.valor * contas.escala = real value in R$
Values in DB are already scaled (Petrobras Ativo Total shows 1.2T correctly).

FUTURE: B3 LINK
---------------
isin table (in rapina.db) has cnpj in numeric format.
b3_api Instruments table has ISIN column.
The join path: b3_api.ticker -> b3_api.ISIN -> rapina.isin.cnpj -> empresas.cnpj
This v1 exposes cnpj + isin_data in query results to enable that join later.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from skills.cvm.catalog import (
    CVM_DB_PATH,
    GRUPOS,
    MESES_LABELS,
    RESUMO_ACCOUNTS,
    RESUMO_BY_GRUPO,
    RESUMO_LOOKUP,
    format_cnpj,
    normalize_cnpj,
    real_value,
)


# ---------------------------------------------------------------------------
# DB connection helper
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """
    Open rapina.db as read-only.
    Raises FileNotFoundError with a clear message if not found.

    DECISION: read-only URI mode (uri=True with ?mode=ro) prevents accidental
    writes and allows concurrent reads without WAL conflicts.
    rapina.db is updated externally by rapinav2 -- this skill never writes.
    """
    if not CVM_DB_PATH.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {CVM_DB_PATH}. "
            f"Move it there: mkdir {CVM_DB_PATH.parent} && copy rapina.db {CVM_DB_PATH}"
        )
    uri = f"file:{CVM_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Company resolution
# ---------------------------------------------------------------------------

def _resolve_company(conn: sqlite3.Connection, query: str) -> list[dict]:
    """
    Find company records in empresas by CNPJ or name.
    Returns list of {id, cnpj, nome, ano} dicts for ALL years found.
    Multiple rows = same company across multiple years (expected).

    Resolution order:
      1. CNPJ match (strips formatting for comparison)
      2. Exact name match (case-insensitive)
      3. Partial name match

    DECISION: return ALL year rows so the caller can decide which years to use.
    Filtering to specific years happens in the query functions.
    """
    q = query.strip()
    rows: list[sqlite3.Row] = []

    # 1. CNPJ lookup -- normalize both sides to numeric for comparison
    q_numeric = normalize_cnpj(q)
    if len(q_numeric) >= 8:  # at least partial CNPJ
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') "
            "LIKE ? ORDER BY ano DESC",
            (f"%{q_numeric}%",),
        ).fetchall()

    # 2. Exact name match
    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE UPPER(nome) = UPPER(?) ORDER BY ano DESC",
            (q,),
        ).fetchall()

    # 3. Partial name match
    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE nome LIKE ? ORDER BY ano DESC",
            (f"%{q}%",),
        ).fetchall()

    return [dict(r) for r in rows]


def _isin_for_cnpj(conn: sqlite3.Connection, cnpj_formatted: str) -> list[dict]:
    """
    Look up ISIN records for a company by CNPJ.
    Returns list of {key, ticker, cnpj, nome} from isin table.

    NOTE: isin.cnpj is numeric (no dots/slashes).
    Used to expose ISIN data for future b3_api join.
    """
    cnpj_numeric = normalize_cnpj(cnpj_formatted)
    rows = conn.execute(
        "SELECT key, ticker, cnpj, nome FROM isin WHERE cnpj = ? LIMIT 10",
        (cnpj_numeric,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Core data query
# ---------------------------------------------------------------------------

def _query_contas(
    conn:          sqlite3.Connection,
    empresa_ids:   list[int],
    grupos:        list[str] | None,
    meses_filter:  list[int],
    consolidado:   int,
    anos:          list[int] | None,
    codigo_filter: list[str] | None,
) -> list[dict]:
    """
    Core contas query. Returns rows sorted by data_fim_exerc DESC, grupo, codigo.

    empresa_ids   -- list of empresas.id values (all years for the company)
    grupos        -- filter by statement type (None = all)
    meses_filter  -- list of meses values to include
    consolidado   -- 1=consolidated, 0=individual
    anos          -- filter by year of data_fim_exerc (None = all)
    codigo_filter -- filter to specific account codes (None = all)
    """
    if not empresa_ids:
        return []

    placeholders_ids = ",".join("?" * len(empresa_ids))
    params: list[Any] = list(empresa_ids)

    where_parts = [
        f"c.id_empresa IN ({placeholders_ids})",
        "c.consolidado = ?",
    ]
    params.append(consolidado)

    # meses filter
    placeholders_m = ",".join("?" * len(meses_filter))
    where_parts.append(f"c.meses IN ({placeholders_m})")
    params.extend(meses_filter)

    # grupo filter
    if grupos:
        placeholders_g = ",".join("?" * len(grupos))
        where_parts.append(f"c.grupo IN ({placeholders_g})")
        params.extend(grupos)

    # year filter (on data_fim_exerc)
    if anos:
        year_parts = " OR ".join("CAST(SUBSTR(c.data_fim_exerc,1,4) AS INTEGER) = ?" for _ in anos)
        where_parts.append(f"({year_parts})")
        params.extend(anos)

    # account code filter
    if codigo_filter:
        placeholders_c = ",".join("?" * len(codigo_filter))
        where_parts.append(f"c.codigo IN ({placeholders_c})")
        params.extend(codigo_filter)

    sql = f"""
        SELECT
            c.id_empresa,
            c.codigo,
            c.descr,
            c.grupo,
            c.consolidado,
            c.data_ini_exerc,
            c.data_fim_exerc,
            c.meses,
            c.valor,
            c.escala,
            c.valor * c.escala AS valor_real,
            c.moeda,
            e.cnpj,
            e.nome,
            e.ano AS empresa_ano
        FROM contas c
        JOIN empresas e ON e.id = c.id_empresa
        WHERE {' AND '.join(where_parts)}
        ORDER BY c.data_fim_exerc DESC, c.grupo, c.codigo
    """

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Result formatters
# ---------------------------------------------------------------------------

def _format_completo(rows: list[dict], company_info: dict) -> dict:
    """
    Format completo output: all accounts grouped by period then statement type.

    Structure:
      {
        "company": {...},
        "periods": {
          "2025-12-31": {
            "meses": 12, "label": "Annual (12m)",
            "BPA": [{"codigo": "1", "descr": "...", "valor": 1223389000000}],
            "DRE": [...],
            ...
          }
        }
      }
    """
    periods: dict[str, dict] = {}

    for row in rows:
        date = row["data_fim_exerc"]
        if date not in periods:
            meses = row["meses"]
            periods[date] = {
                "date":   date,
                "meses":  meses,
                "label":  MESES_LABELS.get(meses, f"{meses}m"),
                "groups": {},
            }
        grupo = row["grupo"]
        if grupo not in periods[date]["groups"]:
            periods[date]["groups"][grupo] = {
                "name":     GRUPOS.get(grupo, grupo),
                "accounts": [],
            }
        periods[date]["groups"][grupo]["accounts"].append({
            "codigo":     row["codigo"],
            "descr":      row["descr"],
            "valor":      row["valor_real"],
            "moeda":      row["moeda"] or "R$",
        })

    return {
        "company": company_info,
        "periods": periods,
        "period_count": len(periods),
    }


def _format_resumo(rows: list[dict], company_info: dict) -> dict:
    """
    Format resumo output: key metrics only, pivoted for easy reading.

    Structure:
      {
        "company": {...},
        "metrics": {
          "Receita Líquida": {
            "codigo": "3.01", "grupo": "DRE", "label_en": "Net Revenue",
            "values": {"2025-12-31": 12345678, "2024-12-31": 11234567}
          },
          ...
        },
        "periods": ["2025-12-31", "2024-12-31", ...]
      }
    """
    # Collect all distinct periods in order
    seen_periods: list[str] = []
    period_meta: dict[str, dict] = {}
    for row in rows:
        d = row["data_fim_exerc"]
        if d not in period_meta:
            seen_periods.append(d)
            period_meta[d] = {
                "meses": row["meses"],
                "label": MESES_LABELS.get(row["meses"], f"{row['meses']}m"),
            }

    # Build metrics dict in canonical RESUMO_ACCOUNTS order
    metrics: dict[str, dict] = {}
    for code, grupo, lpt, len_ in RESUMO_ACCOUNTS:
        key = lpt  # Portuguese label as the metric key
        metrics[key] = {
            "codigo":   code,
            "grupo":    grupo,
            "label_pt": lpt,
            "label_en": len_,
            "values":   {},   # date -> valor_real
        }

    # Fill values from rows
    for row in rows:
        code  = row["codigo"]
        grupo = row["grupo"]
        date  = row["data_fim_exerc"]
        key_lookup = (code, grupo)
        if key_lookup in RESUMO_LOOKUP:
            lpt, _ = RESUMO_LOOKUP[key_lookup]
            if lpt in metrics:
                metrics[lpt]["values"][date] = row["valor_real"]

    # Remove metrics with no data
    metrics = {k: v for k, v in metrics.items() if v["values"]}

    return {
        "company":      company_info,
        "metrics":      metrics,
        "periods":      seen_periods,
        "period_meta":  period_meta,
        "metric_count": len(metrics),
    }


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def _run_query(
    company:     str,
    mode:        str,   # "completo_anual"|"completo_trim"|"resumo_anual"|"resumo_trim"
    anos:        list[int] | None,
    consolidado: int,
    limit_years: int,
) -> dict:
    """
    Shared query runner for all four modes.
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        # Resolve company
        emp_rows = _resolve_company(conn, company)
        if not emp_rows:
            return {
                "status": "error",
                "error":  f"Company '{company}' not found in rapina.db. "
                          f"Try the full name or CNPJ (e.g. '33.000.167/0001-01').",
            }

        # If multiple companies matched (name search), use the one with most records
        # Group by CNPJ to detect genuine multiple matches
        by_cnpj: dict[str, list[dict]] = {}
        for r in emp_rows:
            by_cnpj.setdefault(r["cnpj"], []).append(r)

        if len(by_cnpj) > 1:
            # Multiple distinct companies -- return list for disambiguation
            return {
                "status":   "ambiguous",
                "error":    f"'{company}' matched {len(by_cnpj)} companies. Use CNPJ or full name.",
                "matches":  [
                    {"cnpj": cnpj, "nome": rows[0]["nome"], "anos": [r["ano"] for r in rows]}
                    for cnpj, rows in by_cnpj.items()
                ],
            }

        # Single company -- collect all ids
        all_rows = list(by_cnpj.values())[0]
        cnpj     = all_rows[0]["cnpj"]
        nome     = all_rows[0]["nome"]

        # Apply year filter
        if anos:
            filtered = [r for r in all_rows if r["ano"] in anos]
            if not filtered:
                available = sorted({r["ano"] for r in all_rows}, reverse=True)
                return {
                    "status": "error",
                    "error":  f"No data for {nome} in years {anos}. Available: {available}",
                }
            all_rows = filtered
        else:
            # Limit to most recent N years
            sorted_rows = sorted(all_rows, key=lambda r: r["ano"], reverse=True)
            all_rows = sorted_rows[:limit_years]

        empresa_ids = [r["id"] for r in all_rows]
        years_queried = sorted({r["ano"] for r in all_rows}, reverse=True)

        # Determine meses filter and whether to get resumo codes only
        is_anual  = "anual" in mode
        is_resumo = "resumo" in mode

        meses_filter  = [12] if is_anual else [3, 6, 9]
        codigo_filter = None

        if is_resumo:
            # Collect all resumo codes across all grupos
            codigo_filter = list({code for code, _, _, _ in RESUMO_ACCOUNTS})

        # Run the query
        rows = _query_contas(
            conn          = conn,
            empresa_ids   = empresa_ids,
            grupos        = None,   # all grupos
            meses_filter  = meses_filter,
            consolidado   = consolidado,
            anos          = None,   # already filtered via empresa_ids
            codigo_filter = codigo_filter,
        )

        if not rows:
            return {
                "status": "error",
                "error":  (
                    f"No {'consolidated' if consolidado else 'individual'} "
                    f"{'annual' if is_anual else 'quarterly'} data found for {nome}. "
                    f"Years queried: {years_queried}. "
                    f"Try consolidado=0 for individual statements."
                ),
            }

        # Get ISIN cross-reference for future b3_api join
        isin_data = _isin_for_cnpj(conn, cnpj)

        company_info = {
            "nome":         nome,
            "cnpj":         cnpj,
            "cnpj_numeric": normalize_cnpj(cnpj),
            "anos":         years_queried,
            "isin_records": isin_data,  # for future b3_api ISIN join
        }

        # Format output
        if is_resumo:
            result = _format_resumo(rows, company_info)
        else:
            result = _format_completo(rows, company_info)

        result["status"] = "ok"
        result["mode"]   = mode
        result["rows_raw"] = len(rows)
        return result

    except Exception as e:
        return {"status": "error", "error": f"Query failed: {type(e).__name__}: {e}"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Four public entry points (one per sheet type)
# ---------------------------------------------------------------------------

def completo_anual(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 5,
) -> dict:
    """
    All account codes, annual data (meses=12), consolidated by default.
    Equivalent to rapinav2 "completo anual (consolid)" sheet.

    company:     company name, partial name, or CNPJ
    anos:        specific years to return (e.g. [2023, 2024]). Default: last 5.
    consolidado: 1=consolidated (default), 0=individual statements
    limit_years: max years to return when anos not specified (default 5)
    """
    return _run_query(company, "completo_anual", anos, consolidado, limit_years)


def completo_trim(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 3,
) -> dict:
    """
    All account codes, quarterly data (meses=3/6/9), consolidated by default.
    Equivalent to rapinav2 "completo trim. (consolid)" sheet.

    NOTE: meses=6 is H1 cumulative (Jan-Jun), NOT standalone Q2.
          meses=9 is 9-month cumulative, NOT standalone Q3.
          True standalone quarters require period subtraction (v2 feature).

    company:     company name, partial name, or CNPJ
    anos:        specific years (default: last 3 years of quarterly filings)
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years when anos not specified (default 3)
    """
    return _run_query(company, "completo_trim", anos, consolidado, limit_years)


def resumo_anual(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
) -> dict:
    """
    Key metrics only, annual data (meses=12), consolidated by default.
    Equivalent to rapinav2 "resumo anual (consolid)" sheet.

    Metrics included (20 total):
      Income: Receita Líquida, COGS, Gross Profit, EBIT, Financial Result,
              Pre-tax Income, Income Tax, Net Income
      Balance: Total Assets, Current Assets, Cash, Non-Current Assets,
               Total Liabilities, Current Liab., Non-Current Liab., Equity
      Cash Flow: Operating, Investing, Financing, Net Change

    company:     company name, partial name, or CNPJ
    anos:        specific years (default: last 10 years)
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years when anos not specified (default 10)
    """
    return _run_query(company, "resumo_anual", anos, consolidado, limit_years)


def resumo_trim(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 4,
) -> dict:
    """
    Key metrics only, quarterly data (meses=3/6/9), consolidated by default.
    Equivalent to rapinav2 "resumo trim. (consolid)" sheet.

    NOTE: periods are cumulative within the year (see completo_trim note).

    company:     company name, partial name, or CNPJ
    anos:        specific years (default: last 4 years of quarterly filings)
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years when anos not specified (default 4)
    """
    return _run_query(company, "resumo_trim", anos, consolidado, limit_years)


def search_companies(query: str, limit: int = 10) -> dict:
    """
    Search for companies by name or CNPJ fragment.
    Returns distinct companies (deduplicated by CNPJ) with available year range.

    Useful for finding the exact name/CNPJ before running a full query.
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        q_numeric = normalize_cnpj(query)
        if len(q_numeric) >= 8:
            rows = conn.execute(
                "SELECT cnpj, nome, MIN(ano) as ano_min, MAX(ano) as ano_max, COUNT(*) as years "
                "FROM empresas "
                "WHERE REPLACE(REPLACE(REPLACE(cnpj,'.',''),'/',''),'-','') LIKE ? "
                "GROUP BY cnpj ORDER BY nome LIMIT ?",
                (f"%{q_numeric}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT cnpj, nome, MIN(ano) as ano_min, MAX(ano) as ano_max, COUNT(*) as years "
                "FROM empresas WHERE nome LIKE ? "
                "GROUP BY cnpj ORDER BY nome LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()

        companies = [
            {
                "cnpj":    r["cnpj"],
                "nome":    r["nome"],
                "anos":    f"{r['ano_min']}-{r['ano_max']}",
                "years":   r["years"],
            }
            for r in rows
        ]
        return {
            "status":  "ok",
            "query":   query,
            "count":   len(companies),
            "results": companies,
        }
    finally:
        conn.close()


def db_status() -> dict:
    """
    Return rapina.db status: file size, row counts, date range, last update.
    """
    if not CVM_DB_PATH.exists():
        return {
            "status":  "not_found",
            "error":   f"rapina.db not found at {CVM_DB_PATH}",
            "db_path": str(CVM_DB_PATH),
        }

    size_mb = round(CVM_DB_PATH.stat().st_size / 1024 / 1024, 1)
    try:
        conn = _connect()
        contas_count  = conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0]
        empresas_count = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        date_range    = conn.execute(
            "SELECT MIN(data_fim_exerc), MAX(data_fim_exerc) FROM contas"
        ).fetchone()
        conn.close()
        return {
            "status":       "ok",
            "db_path":      str(CVM_DB_PATH),
            "size_mb":      size_mb,
            "contas_rows":  contas_count,
            "empresas_rows": empresas_count,
            "date_from":    date_range[0],
            "date_to":      date_range[1],
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "db_path": str(CVM_DB_PATH)}
