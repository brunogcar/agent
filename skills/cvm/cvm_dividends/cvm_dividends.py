"""
skills/cvm/cvm_dividends/cvm_dividends.py -- Dividend data from rapina.db.

Three query modes:
  annual   -- DVA dividends + JCP per fiscal year (primary, ~10K companies)
  declared -- BPP dividends declared/payable at balance sheet date
  cash     -- DFC actual cash paid for dividends and JCP

All modes share the same company resolution pattern as cvm_api:
  name/CNPJ → empresas (all year ids) → contas (filter by codes + meses)

See cvm_dividends_catalog.py for full account code documentation.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skills.cvm.cvm_dividends.cvm_dividends_catalog import (
    RAPINA_DB,
    DVA_DIVIDEND_CODES,
    DVA_KEY_CODES,
    BPP_DIVIDEND_CODES,
    DFC_CODE_LIST,
    get_label,
)


# ---------------------------------------------------------------------------
# DB + company resolution (mirrors cvm_api pattern)
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    if not RAPINA_DB.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {RAPINA_DB}. "
            "Move it there or update rapinav2: rapinav2 atualizar --all"
        )
    conn = sqlite3.connect(f"file:{RAPINA_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


def _resolve_company(conn: sqlite3.Connection, company: str) -> tuple[list[dict], str]:
    """
    Find all empresas rows for a company (by CNPJ or name).
    Returns (rows, error). rows is empty on error.
    Same pattern as cvm_api._resolve_company.
    """
    q = company.strip()
    rows = []

    # CNPJ match
    q_numeric = _normalize_cnpj(q)
    if len(q_numeric) >= 8:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj,'.',''),'/',''),'-','') LIKE ? "
            "ORDER BY ano DESC",
            (f"%{q_numeric}%",),
        ).fetchall()

    # Exact name
    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE UPPER(nome) = UPPER(?) ORDER BY ano DESC",
            (q,),
        ).fetchall()

    # Partial name
    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE nome LIKE ? ORDER BY ano DESC",
            (f"%{q}%",),
        ).fetchall()

    if not rows:
        return [], f"Company '{company}' not found in rapina.db."

    # Check for ambiguous multi-company match
    by_cnpj: dict[str, list] = {}
    for r in rows:
        by_cnpj.setdefault(r["cnpj"], []).append(dict(r))

    if len(by_cnpj) > 1:
        return [], (
            f"'{company}' matched {len(by_cnpj)} companies. "
            f"Use CNPJ or full name. Matches: "
            + ", ".join(f"{v[0]['nome']} ({k})" for k, v in list(by_cnpj.items())[:5])
        )

    return [dict(r) for r in rows], ""


def _get_ids(emp_rows: list[dict], anos: list[int] | None, limit_years: int) -> list[int]:
    """Filter empresa rows to requested years and return id list."""
    if anos:
        filtered = [r for r in emp_rows if r["ano"] in anos]
    else:
        sorted_rows = sorted(emp_rows, key=lambda r: r["ano"], reverse=True)
        filtered = sorted_rows[:limit_years]
    return [r["id"] for r in filtered]


def _query_contas(
    conn:        sqlite3.Connection,
    ids:         list[int],
    grupo:       str,
    codes:       list[str],
    meses:       list[int],
    consolidado: int,
) -> list[dict]:
    if not ids or not codes:
        return []
    ph_ids   = ",".join("?" * len(ids))
    ph_codes = ",".join("?" * len(codes))
    ph_meses = ",".join("?" * len(meses))
    sql = f"""
        SELECT c.codigo, c.descr, c.valor * c.escala AS valor_real,
               c.data_fim_exerc, c.meses, c.moeda,
               e.nome, e.cnpj, e.ano AS empresa_ano
        FROM contas c
        JOIN empresas e ON e.id = c.id_empresa
        WHERE c.id_empresa IN ({ph_ids})
          AND c.grupo      = ?
          AND c.codigo     IN ({ph_codes})
          AND c.meses      IN ({ph_meses})
          AND c.consolidado = ?
        ORDER BY c.data_fim_exerc DESC, c.codigo
    """
    params = [*ids, grupo, *codes, *meses, consolidado]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Pivot helper
# ---------------------------------------------------------------------------

def _pivot_by_period(rows: list[dict], code_label_map: dict[str, str]) -> dict:
    """
    Pivot rows into {date: {label: value}} for clean output.
    Also builds a sorted list of periods.
    """
    periods: dict[str, dict] = {}
    for row in rows:
        date  = row["data_fim_exerc"]
        code  = row["codigo"]
        label = get_label(code, row["descr"])
        val   = row["valor_real"]
        meses = row["meses"]
        if date not in periods:
            periods[date] = {"meses": meses, "values": {}}
        periods[date]["values"][label] = val

    sorted_periods = sorted(periods.keys(), reverse=True)
    return {"periods": periods, "period_order": sorted_periods}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def annual(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
    include_retained: bool = False,
) -> dict:
    """
    Annual dividends and JCP from DVA (Demonstração do Valor Adicionado).
    Primary source -- covers ~10,139 companies from 2009 to present.

    Returns dividends distributed, JCP paid, and total capital remuneration
    per fiscal year. Values are in R$ (already scaled).

    company:          name, partial name, or CNPJ
    anos:             specific years e.g. [2022,2023,2024]. Default: last 10.
    consolidado:      1=consolidated (default), 0=individual
    limit_years:      max years when anos not set. Default: 10.
    include_retained: if True, also include retained earnings (7.08.04.01).
                      Default False -- focused on cash distributed to shareholders.

    NOTE: DVA dividends are TOTAL distributed -- no per-share data here.
    For per-share dividend history, FRE filings are needed (future skill).
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        emp_rows, err = _resolve_company(conn, company)
        if err:
            return {"status": "error", "error": err}

        ids          = _get_ids(emp_rows, anos, limit_years)
        years_used   = sorted({r["ano"] for r in emp_rows if r["id"] in ids}, reverse=True)
        company_info = {"nome": emp_rows[0]["nome"], "cnpj": emp_rows[0]["cnpj"],
                        "anos": years_used}

        # Codes to fetch
        codes = list(DVA_DIVIDEND_CODES.keys())
        if not include_retained:
            codes = [c for c in codes if c != "7.08.04.01"]

        rows = _query_contas(conn, ids, "DVA", codes, [12], consolidado)

        if not rows:
            return {
                "status": "error",
                "error":  f"No DVA dividend data found for {emp_rows[0]['nome']}. "
                          f"Years queried: {years_used}. "
                          f"Try consolidado=0 for individual statements.",
            }

        pivot = _pivot_by_period(rows, DVA_DIVIDEND_CODES)

        return {
            "status":       "ok",
            "mode":         "annual",
            "source":       "DVA (Demonstração do Valor Adicionado)",
            "company":      company_info,
            "periods":      pivot["periods"],
            "period_order": pivot["period_order"],
            "note":         "Values in R$. JCP (Juros sobre Capital Próprio) is Brazil's tax-deductible dividend equivalent. Sum Dividendos + JCP for total shareholder cash remuneration.",
        }
    finally:
        conn.close()


def declared(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 5,
) -> dict:
    """
    Dividends declared but not yet paid, from BPP (Balance Sheet).
    Shows dividends payable as a liability + dividend reserves in equity.

    Useful for: seeing what was declared at year-end before actual payment,
    tracking dividend reserve build-up, proposed additional dividends.

    company:     name, partial name, or CNPJ
    anos:        specific years. Default: last 5.
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years. Default: 5.
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        emp_rows, err = _resolve_company(conn, company)
        if err:
            return {"status": "error", "error": err}

        ids          = _get_ids(emp_rows, anos, limit_years)
        years_used   = sorted({r["ano"] for r in emp_rows if r["id"] in ids}, reverse=True)
        company_info = {"nome": emp_rows[0]["nome"], "cnpj": emp_rows[0]["cnpj"],
                        "anos": years_used}

        rows = _query_contas(
            conn, ids, "BPP",
            list(BPP_DIVIDEND_CODES.keys()),
            [12], consolidado,
        )

        if not rows:
            return {
                "status": "error",
                "error":  f"No BPP dividend payable data found for {emp_rows[0]['nome']}.",
            }

        pivot = _pivot_by_period(rows, BPP_DIVIDEND_CODES)

        return {
            "status":       "ok",
            "mode":         "declared",
            "source":       "BPP (Balanço Patrimonial Passivo)",
            "company":      company_info,
            "periods":      pivot["periods"],
            "period_order": pivot["period_order"],
            "note":         "Dividendos a Pagar = declared but not yet paid at balance sheet date. Reserva Especial = retained for future distribution.",
        }
    finally:
        conn.close()


def cash_paid(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
) -> dict:
    """
    Actual cash paid for dividends and JCP, from DFC (Cash Flow Statement).
    Shows real cash outflow -- may differ from DVA due to timing.

    Note: DFC codes vary across companies (6.03.01, 6.03.02, 6.03.03).
    This function queries all variants and returns whichever the company uses.

    company:     name, partial name, or CNPJ
    anos:        specific years. Default: last 10.
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years. Default: 10.
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        emp_rows, err = _resolve_company(conn, company)
        if err:
            return {"status": "error", "error": err}

        ids          = _get_ids(emp_rows, anos, limit_years)
        years_used   = sorted({r["ano"] for r in emp_rows if r["id"] in ids}, reverse=True)
        company_info = {"nome": emp_rows[0]["nome"], "cnpj": emp_rows[0]["cnpj"],
                        "anos": years_used}

        # Query all DFC code variants -- company uses one or more
        rows = _query_contas(
            conn, ids, "DFC", DFC_CODE_LIST, [12], consolidado,
        )

        if not rows:
            return {
                "status":  "not_found",
                "message": f"No DFC dividend cash flow data found for {emp_rows[0]['nome']}. "
                           "Not all companies use explicit dividend DFC codes. "
                           "Use mode='annual' (DVA) for broader coverage.",
                "company": company_info,
            }

        pivot = _pivot_by_period(rows, {c: d for c, d in
                                        zip(DFC_CODE_LIST, ["Dividendos e JCP Pagos"]*3)})

        return {
            "status":       "ok",
            "mode":         "cash_paid",
            "source":       "DFC (Demonstração do Fluxo de Caixa)",
            "company":      company_info,
            "periods":      pivot["periods"],
            "period_order": pivot["period_order"],
            "note":         "Cash actually paid during the period. Negative values = cash outflow (normal for financing activities).",
        }
    finally:
        conn.close()


def db_status() -> dict:
    """Show rapina.db status relevant to dividend data."""
    if not RAPINA_DB.exists():
        return {"status": "not_found", "error": f"rapina.db not found at {RAPINA_DB}"}
    try:
        conn = _connect()
        dva_rows = conn.execute(
            "SELECT COUNT(*) FROM contas WHERE grupo='DVA' AND codigo LIKE '7.08.04%'"
        ).fetchone()[0]
        companies = conn.execute(
            "SELECT COUNT(DISTINCT id_empresa) FROM contas WHERE grupo='DVA' AND codigo='7.08.04.02'"
        ).fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(data_fim_exerc), MAX(data_fim_exerc) FROM contas WHERE grupo='DVA'"
        ).fetchone()
        conn.close()
        return {
            "status":             "ok",
            "db_path":            str(RAPINA_DB),
            "size_mb":            round(RAPINA_DB.stat().st_size / 1024 / 1024, 1),
            "dva_dividend_rows":  dva_rows,
            "companies_with_div": companies,
            "date_from":          date_range[0],
            "date_to":            date_range[1],
            "primary_source":     "DVA 7.08.04.* (annual + quarterly)",
            "secondary_sources":  "BPP 2.01.05.02.* (declared), DFC 6.03.* (cash paid)",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
