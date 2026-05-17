"""
skills/cvm/cvm_shareholders/cvm_shareholders.py -- Shareholder equity data from rapina.db.

Two query modes:
  equity_structure -- Full BPP 2.03.* equity breakdown (capital, reserves,
                      retained earnings, minority interest) per period.
  minority         -- Minority interest (2.03.09) focus: value over time +
                      minority % of total equity. Useful for conglomerate analysis.

WHAT THIS COVERS
----------------
All data comes from BPP (Balance Sheet) Patrimônio Líquido section.
This gives the VALUE of equity components -- not ownership percentages.
Minority interest (2.03.09) is the only shareholder-split available without FRE.

WHAT THIS DOES NOT COVER (needs FRE -- future cvm_fre skill)
-------------------------------------------------------------
  - Individual shareholder names
  - Ownership percentages (% controlling, % free float, % institutional)
  - Share counts by class (ON, PN, units)
  - Board and management compensation
"""

from __future__ import annotations

import sqlite3

from skills.cvm.cvm_shareholders.cvm_shareholders_catalog import (
    RAPINA_DB,
    EQUITY_CODES,
    EQUITY_SUMMARY_CODES,
    EQUITY_ALL_CODES,
    get_label,
)


# ---------------------------------------------------------------------------
# DB + company resolution (same pattern as cvm_api and cvm_dividends)
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    if not RAPINA_DB.exists():
        raise FileNotFoundError(
            f"rapina.db not found at {RAPINA_DB}. "
            "Update with: rapinav2 atualizar --all"
        )
    conn = sqlite3.connect(f"file:{RAPINA_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


def _resolve_company(conn: sqlite3.Connection, company: str) -> tuple[list[dict], str]:
    q = company.strip()
    rows = []

    q_numeric = _normalize_cnpj(q)
    if len(q_numeric) >= 8:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE REPLACE(REPLACE(REPLACE(cnpj,'.',''),'/',''),'-','') LIKE ? "
            "ORDER BY ano DESC",
            (f"%{q_numeric}%",),
        ).fetchall()

    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE UPPER(nome) = UPPER(?) ORDER BY ano DESC",
            (q,),
        ).fetchall()

    if not rows:
        rows = conn.execute(
            "SELECT id, cnpj, nome, ano FROM empresas "
            "WHERE nome LIKE ? ORDER BY ano DESC",
            (f"%{q}%",),
        ).fetchall()

    if not rows:
        return [], f"Company '{company}' not found in rapina.db."

    by_cnpj: dict[str, list] = {}
    for r in rows:
        by_cnpj.setdefault(r["cnpj"], []).append(dict(r))

    if len(by_cnpj) > 1:
        return [], (
            f"'{company}' matched {len(by_cnpj)} companies. "
            "Use CNPJ or full name. Matches: "
            + ", ".join(f"{v[0]['nome']} ({k})" for k, v in list(by_cnpj.items())[:5])
        )

    return [dict(r) for r in rows], ""


def _get_ids(emp_rows: list[dict], anos: list[int] | None, limit_years: int) -> list[int]:
    if anos:
        filtered = [r for r in emp_rows if r["ano"] in anos]
    else:
        sorted_rows = sorted(emp_rows, key=lambda r: r["ano"], reverse=True)
        filtered = sorted_rows[:limit_years]
    return [r["id"] for r in filtered]


def _query_bpp(
    conn:        sqlite3.Connection,
    ids:         list[int],
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
          AND c.grupo      = 'BPP'
          AND c.codigo     IN ({ph_codes})
          AND c.meses      IN ({ph_meses})
          AND c.consolidado = ?
        ORDER BY c.data_fim_exerc DESC, c.codigo
    """
    params = [*ids, *codes, *meses, consolidado]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _pivot_by_period(rows: list[dict]) -> tuple[dict, list[str]]:
    """Pivot rows into {date: {label: value}}. Returns (periods_dict, sorted_dates)."""
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
    return periods, sorted(periods.keys(), reverse=True)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def equity_structure(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
    summary:     bool = False,
) -> dict:
    """
    Full equity structure from BPP 2.03.* (Patrimônio Líquido).
    Shows capital, reserves, retained earnings, and minority interest over time.

    company:     name, partial name, or CNPJ
    anos:        specific years e.g. [2022,2023,2024]. Default: last 10.
    consolidado: 1=consolidated (default), 0=individual
    limit_years: max years when anos not set. Default: 10.
    summary:     if True, return only top-level codes (2.03, 2.03.01, 2.03.02,
                 2.03.04, 2.03.05, 2.03.06, 2.03.09). Default: False (all codes).

    MINORITY INTEREST NOTE:
    2.03.09 (Participação dos Acionistas Não Controladores) is included.
    It represents non-controlling shareholders' equity in subsidiaries.
    Total equity attributable to parent = 2.03 minus 2.03.09.
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}

    try:
        emp_rows, err = _resolve_company(conn, company)
        if err:
            return {"status": "error", "error": err}

        ids        = _get_ids(emp_rows, anos, limit_years)
        years_used = sorted({r["ano"] for r in emp_rows if r["id"] in ids}, reverse=True)
        company_info = {
            "nome": emp_rows[0]["nome"],
            "cnpj": emp_rows[0]["cnpj"],
            "anos": years_used,
        }

        codes = EQUITY_SUMMARY_CODES if summary else EQUITY_ALL_CODES
        rows  = _query_bpp(conn, ids, codes, [12], consolidado)

        if not rows:
            return {
                "status": "error",
                "error":  f"No equity structure data found for {emp_rows[0]['nome']}. "
                          f"Years queried: {years_used}. "
                          "Try consolidado=0 for individual statements.",
            }

        periods, period_order = _pivot_by_period(rows)

        return {
            "status":       "ok",
            "mode":         "equity_structure",
            "source":       "BPP (Balanço Patrimonial Passivo) 2.03.*",
            "company":      company_info,
            "periods":      periods,
            "period_order": period_order,
            "summary":      summary,
            "note":         (
                "Values in R$. "
                "2.03.09 = Minority Interest (non-controlling shareholders in subsidiaries). "
                "Equity attributable to parent = 2.03 minus 2.03.09. "
                "For ownership %, FRE filings are needed (future cvm_fre skill)."
            ),
        }
    finally:
        conn.close()


def minority(
    company:     str,
    anos:        list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
) -> dict:
    """
    Minority interest (non-controlling shareholders) focus view.
    Returns 2.03 (total equity) and 2.03.09 (minority interest) with
    computed minority % of total equity per period.

    Useful for: understanding how much of consolidated equity belongs
    to minority shareholders in subsidiaries vs the parent company.

    company:     name, partial name, or CNPJ
    anos:        specific years. Default: last 10.
    consolidado: 1=consolidated (default). Individual has no minority interest.
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

        ids        = _get_ids(emp_rows, anos, limit_years)
        years_used = sorted({r["ano"] for r in emp_rows if r["id"] in ids}, reverse=True)
        company_info = {
            "nome": emp_rows[0]["nome"],
            "cnpj": emp_rows[0]["cnpj"],
            "anos": years_used,
        }

        rows = _query_bpp(conn, ids, ["2.03", "2.03.09"], [12], consolidado)

        if not rows:
            return {
                "status":  "not_found",
                "message": f"No equity data found for {emp_rows[0]['nome']}.",
                "company": company_info,
            }

        # Build period summary with minority %
        by_period: dict[str, dict] = {}
        for row in rows:
            date = row["data_fim_exerc"]
            if date not in by_period:
                by_period[date] = {"total_equity": None, "minority_interest": None}
            if row["codigo"] == "2.03":
                by_period[date]["total_equity"] = row["valor_real"]
            elif row["codigo"] == "2.03.09":
                by_period[date]["minority_interest"] = row["valor_real"]

        # Compute minority %
        period_order = sorted(by_period.keys(), reverse=True)
        for date, data in by_period.items():
            total = data.get("total_equity")
            minority_val = data.get("minority_interest")
            if total and minority_val is not None and total != 0:
                data["minority_pct"] = round(abs(minority_val / total) * 100, 2)
                data["parent_equity"] = total - minority_val
            else:
                data["minority_pct"] = None
                data["parent_equity"] = total

        has_minority = any(
            d.get("minority_interest") not in (None, 0)
            for d in by_period.values()
        )

        return {
            "status":       "ok",
            "mode":         "minority",
            "source":       "BPP 2.03 + 2.03.09",
            "company":      company_info,
            "periods":      by_period,
            "period_order": period_order,
            "has_minority_interest": has_minority,
            "note":         (
                "minority_pct = minority interest as % of total consolidated equity. "
                "parent_equity = total equity minus minority interest. "
                "minority_interest=0 or None = company has no non-controlling shareholders."
            ),
        }
    finally:
        conn.close()


def db_status() -> dict:
    """Show rapina.db coverage for shareholder equity data."""
    if not RAPINA_DB.exists():
        return {"status": "not_found", "error": f"rapina.db not found at {RAPINA_DB}"}
    try:
        conn = _connect()
        total_equity = conn.execute(
            "SELECT COUNT(DISTINCT id_empresa) FROM contas WHERE codigo='2.03'"
        ).fetchone()[0]
        minority_cos = conn.execute(
            "SELECT COUNT(DISTINCT id_empresa) FROM contas "
            "WHERE codigo='2.03.09' AND valor != 0"
        ).fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(data_fim_exerc), MAX(data_fim_exerc) "
            "FROM contas WHERE grupo='BPP' AND codigo='2.03'"
        ).fetchone()
        conn.close()
        return {
            "status":                 "ok",
            "db_path":                str(RAPINA_DB),
            "size_mb":                round(RAPINA_DB.stat().st_size / 1024 / 1024, 1),
            "companies_with_equity":  total_equity,
            "companies_with_minority": minority_cos,
            "date_from":              date_range[0],
            "date_to":                date_range[1],
            "note":                   "Full ownership % requires FRE filings (future cvm_fre skill).",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
