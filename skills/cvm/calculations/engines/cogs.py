"""engines/cogs.py -- TTM (trailing twelve months) Cost of Goods Sold engine.

Mirrors engines/revenue.py with one change: CVM account code 3.02
(Custo dos Bens e/ou Serviços Vendidos / COGS) instead of 3.01 (Receita
Liquida). The TTM derivation algorithm is identical.

NOTE: COGS is typically reported as a NEGATIVE figure on the DRE (it's a
cost/deduction from revenue). This engine returns the RAW value from the
database -- callers handle the sign as needed (e.g., gross_profit =
revenue + cogs because cogs is negative; or gross_profit = revenue - |cogs|
if the caller prefers absolute values). Returning the raw value matches
how the DRE itself represents the line.

NO DESCRIPTION-SEARCH FALLBACK
------------------------------
Unlike revenue.py (which needs a description-search fallback for banks/
insurers whose top-line revenue is "Receitas de Intermediação Financeira"
instead of "Receita Liquida"), codigo 3.02 (COGS) is a standard DRE line
that exists uniformly across commercial, industrial, AND financial filers
(banks report it under their cost-of-intermediation section). So this
engine uses a single direct codigo-3.02 query path -- no fallback.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 COGS
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 COGS
  DFP 2023 (meses=12)   = full year 2023 COGS
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM COGS computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.cogs import cogs_at
    c = cogs_at("PETR4", "2024-06-30")  # -> -150000000000.0 (negative cost)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Custo dos Bens e/ou Serviços Vendidos (COGS).
# Standard DRE line for commercial/industrial filers; banks/insurers also
# report their cost-of-intermediation here (or under a sibling code), so a
# direct codigo-3.02 query is sufficient.
COGS_CODE = "3.02"


def _get_dfp_cogs(company: str) -> dict[str, dict]:
    """Get all annual COGS from DFP (codigo 3.02, meses=12).

    Returns: {"2024": {"value": -150e9, "date": "2024-12-31"}, ...}
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
                 AND c.codigo = '{COGS_CODE}'
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


def _get_itr_cogs(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative COGS from ITR (codigo 3.02, meses 3/6/9).

    Returns: {"2024-06-30": {"value": -75e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{COGS_CODE}'
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
def cogs_at(company: str, date: str) -> float | None:
    """Get trailing twelve months COGS ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM COGS in BRL (typically NEGATIVE -- raw DRE value, sign
        preserved), or None if data not available.
    """
    dfp = _get_dfp_cogs(company)
    itr = _get_itr_cogs(company)

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
def cogs_periods(company: str) -> list[dict]:
    """Get all TTM COGS periods for a company.

    Returns a list of {"date": period_end_date, "ttm_cogs": value} sorted oldest-first.
    Each entry represents a point where TTM COGS changed (new ITR/DFP filed).

    Useful for building step-function COGS overlays on price charts.
    """
    dfp = _get_dfp_cogs(company)
    itr = _get_itr_cogs(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = cogs_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_cogs": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_cogs": data["value"]})

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
    name="cogs",
    quantity="ttm_cogs",
    at_fn=cogs_at,
    periods_fn=cogs_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DRE 3.02 -- Custo dos Bens Vendidos TTM",
    category="dre",
))
