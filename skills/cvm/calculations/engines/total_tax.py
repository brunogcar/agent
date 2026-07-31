"""engines/total_tax.py -- TTM (trailing twelve months) Total Tax Burden engine.

This engine mirrors `engines/dva_total_tax.py` 1:1 and is preserved as a
secondary entry point for callers that import via the `total_tax_*`
naming convention. The two engines track the SAME DVA line (Impostos,
Taxas e Contribuições). Prefer `engines/dva_total_tax.py` for new
imports; this file is kept for backwards compatibility.

Mirrors engines/operating_cf.py (DFC 6.01) with one change:
  - CVM account code 7.08.02 (Impostos, Taxas e Contribuições -- total tax
    burden) instead of 6.01 (FCO). New-chart filers use code 7.11.02
    instead — queried in the same SQL via `codigo IN (...)`.

SQL filter: `AND c.grupo LIKE '%Valor Adicionado%' AND c.codigo IN
('7.08.02', '7.11.02')` (the grupo filter is required because the DVA
statement re-uses codigo numbers that overlap with DRE/BPA/BPP/DFC
scopes; the codigo IN covers BOTH the old-chart `7.08.02` and the
new-chart `7.11.02` formats).

DVA = Demonstração do Valor Adicionado (Value Added Statement). A CVM
flow statement showing how wealth is created and distributed. Required
filing for all B3-listed companies, but OPTIONAL for non-listed filers --
so some companies have no DVA rows. The engine returns None gracefully
in that case (the existing `if not itr and not dfp: return None` path).

This is the TOTAL TAX BURDEN -- broader than the `tax` engine (DRE 3.08,
which captures only INCOME TAX). DVA 7.08.02 includes:
  - Income tax (IRPJ + CSLL) -- cross-checks DRE 3.08
  - Indirect taxes on revenue (PIS, COFINS)
  - Taxes on goods/services (ICMS, IPI, ISS)
  - Other contributions (FGTS, INSS -- depending on reporting practice)

For industrial/commercial companies, indirect taxes often dwarf income
tax -- so DVA 7.08.02 gives a more complete picture of the company's total
tax contribution to society. Useful for tax-burden analysis and for
cross-checking effective_tax_rate (DRE 3.08 / EBT) against the broader
DVA figure.

SIGN CONVENTION
---------------
DVA 7.08.02 (Impostos, Taxas e Contribuições) is typically reported as a
NEGATIVE figure on the DVA (it's a wealth OUTFLOW -- taxes distributed
to government). This engine returns the RAW value from the database --
callers handle the sign as needed.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 total tax burden
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 total tax burden
  DFP 2023 (meses=12)   = full year 2023 total tax burden
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM total tax burden computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.total_tax import total_tax_at
    r = total_tax_at("PETR4", "2024-06-30")  # -> -90e9 (negative outflow)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Impostos, Taxas e Contribuições (total tax burden).
# Lives within the DVA statement group.
# Old chart: 7.08.02 (dominant). New chart: 7.11.02 (~75 rows).
# Query both via the SQL `codigo IN (...)` clause below.
TOTAL_TAX_CODE = "7.08.02"
TOTAL_TAX_CODE_NEW = "7.11.02"


def _get_dfp_total_tax(company: str) -> dict[str, dict]:
    """Get all annual total tax burden from DFP (DVA grupo LIKE
    '%Valor Adicionado%', codigo IN ('7.08.02', '7.11.02'), meses=12).

    Returns: {"2024": {"value": -90e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Sign preserved (typically negative).
    """
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
                 AND c.grupo LIKE '%Valor Adicionado%'
                 AND c.codigo IN ('{TOTAL_TAX_CODE}', '{TOTAL_TAX_CODE_NEW}')
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


def _get_itr_total_tax(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative total tax burden from ITR (DVA grupo LIKE
    '%Valor Adicionado%', codigo IN ('7.08.02', '7.11.02'), meses 3/6/9).

    Returns: {"2024-06-30": {"value": -45e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan -> period end).
    Sign preserved (typically negative).
    """
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
                 AND c.grupo LIKE '%Valor Adicionado%'
                 AND c.codigo IN ('{TOTAL_TAX_CODE}', '{TOTAL_TAX_CODE_NEW}')
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
def total_tax_at(company: str, date: str) -> float | None:
    """Get trailing twelve months total tax burden (DVA 7.08.02 or 7.11.02) ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM total tax burden in BRL (typically NEGATIVE -- raw DVA value,
        sign preserved), or None if data not available (e.g., company does
        not file DVA, or insufficient ITR history to derive TTM).
    """
    dfp = _get_dfp_total_tax(company)
    itr = _get_itr_total_tax(company)

    if not itr and not dfp:
        return None

    # Find the most recent ITR period <= date
    itr_dates = sorted([d for d in itr.keys() if d <= date], reverse=True)
    if not itr_dates:
        # No ITR data before this date -- try DFP annual
        dfp_years = sorted([y for y in dfp.keys() if dfp[y]["date"] <= date], reverse=True)
        if dfp_years:
            return dfp[dfp_years[0]]["value"]
        return None

    current_itr_date = itr_dates[0]
    current = itr[current_itr_date]
    current_meses = current["meses"]
    current_year = current["year"]

    # Find same period (same meses) from prior year
    prior_year = current_year - 1
    prior_itr_date = None
    for d, v in itr.items():
        if v["year"] == prior_year and v["meses"] == current_meses:
            prior_itr_date = d
            break

    # Get DFP for prior year
    prior_dfp = dfp.get(str(prior_year))

    if prior_itr_date and prior_dfp:
        # TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period
        ttm = prior_dfp["value"] - itr[prior_itr_date]["value"] + current["value"]
        return ttm
    elif prior_dfp and not prior_itr_date:
        # No ITR for prior year same period -- use DFP directly as approximation
        return prior_dfp["value"]
    elif current and not prior_dfp:
        # No DFP for prior year -- can't derive TTM
        return None
    else:
        return None


@engine_cached
def total_tax_periods(company: str) -> list[dict]:
    """Get all TTM total tax burden (DVA 7.08.02 or 7.11.02) periods for a company.

    Returns a list of {"date": period_end_date, "ttm_total_tax": value}
    sorted oldest-first. Each entry represents a point where TTM total
    tax burden changed (new ITR/DFP filed).

    Useful for building step-function tax-burden overlays on price charts
    or for cross-checking against the tax engine (DRE 3.08, income tax only).
    """
    dfp = _get_dfp_total_tax(company)
    itr = _get_itr_total_tax(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = total_tax_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_total_tax": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_total_tax": data["value"]})

    # Sort and deduplicate by date
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
    name="total_tax",
    quantity="ttm_total_tax",
    at_fn=total_tax_at,
    periods_fn=total_tax_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DVA grupo LIKE '%Valor Adicionado%' codigo 7.08.02 (or 7.11.02) -- Carga Tributária Total TTM",
    category="dva",
))
