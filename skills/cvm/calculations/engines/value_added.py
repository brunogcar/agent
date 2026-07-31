"""engines/value_added.py -- TTM (trailing twelve months) Total Value Added engine.

Mirrors engines/operating_cf.py (DFC 6.01) with one change:
  - CVM account code 7.08 (Valor Adicionado Total a Distribuir -- total
    wealth created by the company) instead of 6.01 (FCO). New-chart filers
    use code 7.10 instead — queried in the same SQL via `codigo IN (...)`.

SQL filter: `AND c.grupo LIKE '%Valor Adicionado%' AND c.codigo IN
('7.08', '7.10')` (the grupo filter is required because the DVA
statement re-uses codigo numbers that overlap with DRE/BPA/BPP/DFC
scopes; the codigo IN covers BOTH the old-chart `7.08` and the
new-chart `7.10` formats).

DVA = Demonstração do Valor Adicionado (Value Added Statement). A CVM
flow statement showing how wealth is created and distributed. Required
filing for all B3-listed companies, but OPTIONAL for non-listed filers --
so some companies have no DVA rows. The engine returns None gracefully
in that case (the existing `if not itr and not dfp: return None` path).

DVA 7.08 (Valor Adicionado Total a Distribuir) is the TOP LINE of the
"distribution" side of the DVA. It equals the sum of all wealth
distributed to:
  - Personnel (8.1)
  - Government (8.2) -- captured separately by total_tax
  - Lenders / third-party capital (8.3) -- captured by interest_paid
  - Shareholders / own capital (8.4)

And it equals the "generation" side of the DVA:
  - Revenues (1) - Inputs (2) = Gross value added (3)
  - + Retentions (4) - Depreciation (5 adjustments) = Net value added produced (5)
  - + Value received in transfer (6) = Total value added to distribute (7)

So DVA 7.08 is conceptually similar to EBITDA but with a different scope
(it captures wealth created for ALL stakeholders, not just shareholders +
lenders). Useful for stakeholder-distribution analysis and for verifying
the consistency of the DVA itself (7.08 should = 7.08.01 + 7.08.02 +
7.08.03 + 7.08.04).

SIGN CONVENTION
---------------
DVA 7.08 (Valor Adicionado Total a Distribuir) is typically reported as a
POSITIVE figure on the DVA (it's the total wealth available for
distribution). This engine returns the RAW value from the database --
callers handle the sign as needed.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 total value added
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 total value added
  DFP 2023 (meses=12)   = full year 2023 total value added
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM value added computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.value_added import value_added_at
    r = value_added_at("PETR4", "2024-06-30")  # -> 250e9 (positive wealth created)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Valor Adicionado Total a Distribuir (total wealth
# created by the company, available for distribution to stakeholders).
# Lives within the DVA statement group.
# Old chart: 7.08 (dominant — 16808 rows in DFP). New chart: 7.10 (~75
# rows). Query both via the SQL `codigo IN (...)` clause below.
VALUE_ADDED_CODE = "7.08"
VALUE_ADDED_CODE_NEW = "7.10"


def _get_dfp_value_added(company: str) -> dict[str, dict]:
    """Get all annual total value added from DFP (DVA grupo LIKE
    '%Valor Adicionado%', codigo IN ('7.08', '7.10'), meses=12).

    Returns: {"2024": {"value": 250e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Sign preserved (typically positive).
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
                 AND c.codigo IN ('{VALUE_ADDED_CODE}', '{VALUE_ADDED_CODE_NEW}')
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


def _get_itr_value_added(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative total value added from ITR (DVA grupo LIKE
    '%Valor Adicionado%', codigo IN ('7.08', '7.10'), meses 3/6/9).

    Returns: {"2024-06-30": {"value": 125e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan -> period end).
    Sign preserved (typically positive).
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
                 AND c.codigo IN ('{VALUE_ADDED_CODE}', '{VALUE_ADDED_CODE_NEW}')
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
def value_added_at(company: str, date: str) -> float | None:
    """Get trailing twelve months total value added (DVA 7.08 or 7.10) ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM total value added in BRL (typically POSITIVE -- raw DVA
        value, sign preserved), or None if data not available (e.g.,
        company does not file DVA, or insufficient ITR history to
        derive TTM).
    """
    dfp = _get_dfp_value_added(company)
    itr = _get_itr_value_added(company)

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
def value_added_periods(company: str) -> list[dict]:
    """Get all TTM total value added (DVA 7.08 or 7.10) periods for a company.

    Returns a list of {"date": period_end_date, "ttm_value_added": value}
    sorted oldest-first. Each entry represents a point where TTM total
    value added changed (new ITR/DFP filed).

    Useful for building step-function value-added overlays on price charts
    or for stakeholder-distribution analysis (DVA 7.08 should equal the sum
    of DVA 7.08.01 + 7.08.02 + 7.08.03 + 7.08.04).
    """
    dfp = _get_dfp_value_added(company)
    itr = _get_itr_value_added(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = value_added_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_value_added": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_value_added": data["value"]})

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
    name="value_added",
    quantity="ttm_value_added",
    at_fn=value_added_at,
    periods_fn=value_added_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DVA grupo LIKE '%Valor Adicionado%' codigo 7.08 (or 7.10) -- Valor Adicionado Total TTM",
    category="dva",
))
