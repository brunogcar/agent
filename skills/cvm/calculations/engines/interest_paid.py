"""engines/interest_paid.py -- TTM (trailing twelve months) Interest Paid engine.

Mirrors engines/operating_cf.py (DFC 6.01) with two changes:
  1. CVM account code 8.3 (Remuneração do Capital de Terceiros -- interest
     paid to third-party capital providers) instead of 6.01 (FCO).
  2. SQL filter includes `AND c.grupo = 'DVA'` because the DVA statement
     re-uses codigo numbers that overlap with DRE/BPA/BPP/DFC scopes. Without
     the grupo filter, `codigo = '8.3'` would match nothing (or, in some
     schema versions, match the wrong statement).

DVA = Demonstração do Valor Adicionado (Value Added Statement). A CVM
flow statement showing how wealth is created and distributed. Required
filing for all B3-listed companies, but OPTIONAL for non-listed filers --
so some companies have no DVA rows. The engine returns None gracefully
in that case (the existing `if not itr and not dfp: return None` path).

This is the INTEREST PAID (gross) -- not net financial result. It
cross-checks the financial_result engine (DRE 3.06), which returns the
NET financial result (income - expense). When 8.3 is significantly larger
in magnitude than 3.06, the company has material offsetting financial
income (e.g., interest on cash holdings). DVA 8.3 isolates the gross
interest burden on debt only.

SIGN CONVENTION
---------------
DVA 8.3 (Remuneração do Capital de Terceiros) is typically reported as a
NEGATIVE figure on the DVA (it's a wealth OUTFLOW -- interest paid to
lenders). This engine returns the RAW value from the database -- callers
handle the sign as needed.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 interest paid
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 interest paid
  DFP 2023 (meses=12)   = full year 2023 interest paid
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM interest paid computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.interest_paid import interest_paid_at
    r = interest_paid_at("PETR4", "2024-06-30")  # -> -8e9 (negative outflow)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for Remuneração do Capital de Terceiros (interest paid to
# third-party capital). Lives within the DVA statement group.
INTEREST_PAID_CODE = "8.3"

# DVA statement group identifier in the CVM database. Without this filter,
# codigo = '8.3' would match nothing (DVA codes are scoped to the DVA group).
DVA_GRUPO = "DVA"


def _get_dfp_interest_paid(company: str) -> dict[str, dict]:
    """Get all annual interest paid from DFP (DVA grupo='DVA', codigo 8.3, meses=12).

    Returns: {"2024": {"value": -8e9, "date": "2024-12-31"}, ...}
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
                 AND c.grupo = '{DVA_GRUPO}'
                 AND c.codigo = '{INTEREST_PAID_CODE}'
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


def _get_itr_interest_paid(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative interest paid from ITR (DVA grupo='DVA',
    codigo 8.3, meses 3/6/9).

    Returns: {"2024-06-30": {"value": -4e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.grupo = '{DVA_GRUPO}'
                 AND c.codigo = '{INTEREST_PAID_CODE}'
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


def interest_paid_at(company: str, date: str) -> float | None:
    """Get trailing twelve months interest paid (DVA 8.3) ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM interest paid in BRL (typically NEGATIVE -- raw DVA value,
        sign preserved), or None if data not available (e.g., company does
        not file DVA, or insufficient ITR history to derive TTM).
    """
    dfp = _get_dfp_interest_paid(company)
    itr = _get_itr_interest_paid(company)

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


def interest_paid_periods(company: str) -> list[dict]:
    """Get all TTM interest paid (DVA 8.3) periods for a company.

    Returns a list of {"date": period_end_date, "ttm_interest_paid": value}
    sorted oldest-first. Each entry represents a point where TTM interest
    paid changed (new ITR/DFP filed).

    Useful for building step-function interest-paid overlays on price charts
    or for cross-checking against the financial_result engine (DRE 3.06).
    """
    dfp = _get_dfp_interest_paid(company)
    itr = _get_itr_interest_paid(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = interest_paid_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_interest_paid": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_interest_paid": data["value"]})

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
    name="interest_paid",
    quantity="ttm_interest_paid",
    at_fn=interest_paid_at,
    periods_fn=interest_paid_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DVA grupo='DVA' codigo 8.3 -- Juros Pagos TTM",
    category="dva",
))
