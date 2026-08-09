"""engines/dre/tax.py -- TTM income tax (IR + CSLL) engine.

Mirrors engines/dre/revenue.py with CVM account code 3.08 (Imposto de Renda e
Contribuição Social sobre o Lucro). The TTM derivation algorithm is identical.

Tax is a FLOW (cumulative over the year, like earnings/revenue). We derive
TTM tax using the same DFP + ITR algorithm:
  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

The tax value is typically NEGATIVE (it's an expense/deduction on the DRE).
We return the raw value -- callers decide how to interpret the sign.

DESCRIPTION-SEARCH FALLBACK
---------------------------
For commercial/industrial filers, codigo 3.08 is "Imposto de Renda e
Contribuição Social sobre o Lucro". For financial-sector filers (banks/
insurers), however, the DRE template shifts the tax line to a different
position under the 3.* range, with descriptions like "IRPJ", "CSLL", or
"Contribuição Social". The reference implementation (rapinav2) handles
this with a wildcard + mandatory description match: codigo '3.*' +
descricao LIKE '%Imposto de Renda%' (or 'IRPJ' / 'CSLL' / etc.).  We
mirror that approach as a FALLBACK: the fast path tries the exact 3.08
code (works for the vast majority of filers and is O(1) on the codigo
index), and only if that returns nothing do we fall back to the
description search within the 3.* DRE range.

DATA SOURCE
-----------
DFP DRE codigo 3.08 = "Imposto de Renda e Contribuição Social sobre o Lucro"
  - Annual (meses=12)
ITR DRE codigo 3.08
  - Quarterly cumulative (meses=3/6/9)

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly cumulative)
TTM tax computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dre.tax import tax_at
    t = tax_at("PETR4", "2024-06-30")  # -> -35e9 (negative = expense)
"""
from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for income tax (IR + CSLL). Standard position in the DRE
# for commercial/industrial filers. Banks/insurers may shift this to a
# different 3.* position with descriptions like "IRPJ", "CSLL", or
# "Contribuição Social" -- we fall back to a description-based search when
# 3.08 returns nothing.
INCOME_TAX_CODE = "3.08"

# Description stems used for the fallback search.  We match on partial
# stems (not the full string) so minor wording variations across filers
# are caught.  Banks/insurers may use "IRPJ" / "CSLL" as separate lines.
_INCOME_TAX_DESC_STEMS = (
    "Imposto de Renda",
    "IRPJ",
    "CSLL",
    "Contribuicao Social",
)


@engine_cached
def _get_dfp_tax(company: str) -> dict[str, dict]:
    """Get all annual income tax from DFP (codigo 3.08, meses=12).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.08 code returns nothing -- handles banks/insurers whose
    DRE structure splits the tax line into IRPJ/CSLL components or uses a
    different position.

    Returns: {"2024": {"value": -35e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Typically negative (expense).
    """
    result = _get_dfp_tax_by_code(company, INCOME_TAX_CODE)
    if result:
        return result
    # Fallback: description search within DRE (3.*) for filers where 3.08
    # doesn't land on the tax line (banks/insurers with split IRPJ/CSLL).
    return _get_dfp_tax_by_desc(company)


@engine_cached
def _get_dfp_tax_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.08). Returns {} if nothing found."""
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo = '{code}'
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            empresa_ids,
        ).fetchall()

        result = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            result[str(r["ano"])] = {
                "value": valor,
                "date": r["data_fim_exerc"],
            }
        return result
    finally:
        conn.close()


@engine_cached
def _get_dfp_tax_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by income-tax description stems.

    Used when the exact 3.08 code doesn't match (banks/insurers with split
    IRPJ/CSLL components, or non-standard DRE filers). Mirrors rapinav2's
    wildcard + description-match approach. Sums all matching rows per year
    so that split IRPJ + CSLL lines collapse into a single tax expense value.
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _INCOME_TAX_DESC_STEMS
        )
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo LIKE '3.%'
                 AND ({desc_clause})
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            empresa_ids,
        ).fetchall()

        # Banks may split IRPJ and CSLL into separate rows under 3.* -- sum
        # all matching rows per year to recover the total tax expense.
        result = {}
        for r in rows:
            ano = str(r["ano"])
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            if ano not in result:
                result[ano] = {
                    "value": valor,
                    "date": r["data_fim_exerc"],
                }
            else:
                # Sum across split tax lines (IRPJ + CSLL) for the same year.
                result[ano]["value"] += valor
        return result
    finally:
        conn.close()


@engine_cached
def _get_itr_tax(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative income tax from ITR (codigo 3.08, meses 3/6/9).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.08 code returns nothing -- mirrors the DFP fallback.

    Returns: {"2024-06-30": {"value": -17e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan->period end).
    """
    result = _get_itr_tax_by_code(company, INCOME_TAX_CODE)
    if result:
        return result
    return _get_itr_tax_by_desc(company)


@engine_cached
def _get_itr_tax_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.08). Returns {} if nothing found."""
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo = '{code}'
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        result = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            result[r["data_fim_exerc"]] = {
                "value": valor,
                "meses": r["meses"],
                "year": r["ano"],
            }
        return result
    finally:
        conn.close()


@engine_cached
def _get_itr_tax_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by income-tax description stems.

    Sums all matching rows per period so that split IRPJ + CSLL lines
    collapse into a single tax expense value.
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _INCOME_TAX_DESC_STEMS
        )
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo LIKE '3.%'
                 AND ({desc_clause})
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        # Sum across split tax lines (IRPJ + CSLL) for the same period.
        result = {}
        for r in rows:
            date = r["data_fim_exerc"]
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            if date not in result:
                result[date] = {
                    "value": valor,
                    "meses": r["meses"],
                    "year": r["ano"],
                }
            else:
                result[date]["value"] += valor
        return result
    finally:
        conn.close()


@engine_cached
def tax_at(company: str, date: str) -> float | None:
    """Get trailing twelve months income tax ending at or before date.

    Tax values are typically NEGATIVE (expense on DRE). We return the raw
    value -- callers decide how to interpret the sign.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM income tax in BRL (typically negative), or None if no data.
    """
    dfp = _get_dfp_tax(company)
    itr = _get_itr_tax(company)

    if not itr and not dfp:
        return None

    itr_dates = sorted([d for d in itr.keys() if d <= date], reverse=True)
    if not itr_dates:
        dfp_years = sorted([y for y in dfp.keys() if dfp[y]["date"] <= date], reverse=True)
        if dfp_years:
            return dfp[dfp_years[0]]["value"]
        return None

    current_itr_date = itr_dates[0]
    current = itr[current_itr_date]
    current_meses = current["meses"]
    current_year = current["year"]

    prior_year = current_year - 1
    prior_itr_date = None
    for d, v in itr.items():
        if v["year"] == prior_year and v["meses"] == current_meses:
            prior_itr_date = d
            break

    prior_dfp = dfp.get(str(prior_year))

    if prior_itr_date and prior_dfp:
        ttm = prior_dfp["value"] - itr[prior_itr_date]["value"] + current["value"]
        return ttm
    elif prior_dfp and not prior_itr_date:
        return prior_dfp["value"]
    elif current and not prior_dfp:
        return None
    else:
        return None


@engine_cached
def tax_periods(company: str) -> list[dict]:
    """Get all TTM income tax periods for a company.

    Returns: [{"date": period_end_date, "ttm_tax": value}, ...]
    Sorted oldest-first. Values typically negative (expense).
    """
    dfp = _get_dfp_tax(company)
    itr = _get_itr_tax(company)

    if not itr and not dfp:
        return []

    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = tax_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_tax": ttm})

    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_tax": data["value"]})

    periods.sort(key=lambda p: p["date"])
    seen = set()
    result = []
    for p in periods:
        if p["date"] not in seen:
            result.append(p)
            seen.add(p["date"])

    return result


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402
register_engine(EngineSpec(
    name="tax",
    quantity="ttm_tax",
    at_fn=tax_at,
    periods_fn=tax_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DRE 3.08 -- IR+CSLL TTM (with description-search fallback for non-standard filers)",
    category="dre",
))
