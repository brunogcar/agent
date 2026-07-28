"""engines/financing_cf.py -- TTM (trailing twelve months) financing cash flow engine.

Mirrors engines/operating_cf.py with one change: CVM account code 6.03
(Fluxo de Caixa de Financiamento / FCF) instead of 6.01 (FCO). The TTM
derivation algorithm is identical.

NOTE: "FCF" here is "Fluxo de Caixa de Financiamento" (Financing Cash
Flow), NOT "Free Cash Flow". The quantity key is `ttm_fcf` to mirror the
engine name -- callers should remember this is *financing* CF, not free CF.
(Free CF is composed elsewhere as FCO + FCI; see metrics/p_fcf.py.)

FCF (Financing CF) covers the financing section of the DFC:
  - Debt issuance (inflow, positive)
  - Debt repayment (outflow, negative)
  - Dividends paid (outflow, negative)
  - Share buybacks (outflow, negative)
  - Capital injections / equity issuance (inflow, positive)

Values can be either POSITIVE (net issuance -- company raised more capital
than it returned) or NEGATIVE (net distribution -- company returned more
capital to debt/equity holders than it raised). Mature, cash-generating
companies typically show NEGATIVE FCF (they pay dividends + buy back shares
+ repay debt > new issuance).

FCF lives in the DFC (Demonstração do Fluxo de Caixa) statement group,
but the SQL filters by `codigo` directly (same as operating_cf/investing_cf),
which works across all statement groups. No `grupo` filter needed.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 FCF
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 FCF
  DFP 2023 (meses=12)   = full year 2023 FCF
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM FCF computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.financing_cf import financing_cf_at
    r = financing_cf_at("PETR4", "2024-06-30")  # -> -40000000000.0 (net distribution)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for FCF (Fluxo de Caixa de Financiamento).
# NOTE: This is Financing Cash Flow, NOT Free Cash Flow. The quantity key
# `ttm_fcf` mirrors the engine name (financing_cf -> ttm_fcf) but does NOT
# represent Free Cash Flow (which is composed as FCO + FCI in metrics/p_fcf).
FCF_CODE = "6.03"


def _get_dfp_financing_cf(company: str) -> dict[str, dict]:
    """Get all annual FCF from DFP (codigo 6.03, meses=12).

    Returns: {"2024": {"value": -40e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Typically negative (net distribution)
    for mature companies, but can be positive if the company is net-raising
    capital (debt issuance > repayments + dividends).
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
                 AND c.codigo = '{FCF_CODE}'
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


def _get_itr_financing_cf(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative FCF from ITR (codigo 6.03, meses 3/6/9).

    Returns: {"2024-06-30": {"value": -20e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan->period end).
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
                 AND c.codigo = '{FCF_CODE}'
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


def financing_cf_at(company: str, date: str) -> float | None:
    """Get trailing twelve months FCF ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM FCF (Financing CF) in BRL -- positive for net issuance, negative
        for net distribution -- or None if data not available.
    """
    dfp = _get_dfp_financing_cf(company)
    itr = _get_itr_financing_cf(company)

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


def financing_cf_periods(company: str) -> list[dict]:
    """Get all TTM FCF periods for a company.

    Returns a list of {"date": period_end_date, "ttm_fcf": value} sorted oldest-first.
    Each entry represents a point where TTM FCF changed (new ITR/DFP filed).

    Useful for building step-function FCF overlays on price charts.
    """
    dfp = _get_dfp_financing_cf(company)
    itr = _get_itr_financing_cf(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = financing_cf_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_fcf": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_fcf": data["value"]})

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
    name="financing_cf",
    quantity="ttm_fcf",
    at_fn=financing_cf_at,
    periods_fn=financing_cf_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DFC 6.03 -- FCF (Financing CF) TTM",
    category="dfc",
))
