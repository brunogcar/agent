"""engines/da.py -- TTM (trailing twelve months) Depreciação e Amortização (D&A) engine.

This is the most complex historical engine because D&A does not have a single
standardized CVM account code in the DFC. Different filers use different
codigo values (e.g., 6.01.01.02 in DFC_MD, varying codes in DFC_MI) and some
filers split D&A into multiple line items (e.g., "Depreciação e Amortização"
plus separate "Amortização" lines). To handle this, we:

  1. Search by DESCRIPTION, not by codigo: descricao LIKE '%deprec%' OR
     descricao LIKE '%amort%' (case-insensitive).
  2. SUM all matching line items per period (there may be multiple).
  3. Apply TTM derivation (D&A is a flow, like revenue/earnings).

DATA SOURCE
-----------
DFP DFC (Demonstração do Fluxo de Caixa), grupo LIKE '%Fluxo de Caixa%'
  - Matches both DFC_MI (Método Indireto) and DFC_MD (Método Direto)
  - Annual flow at Dec 31 (meses=12)
  - D&A is typically POSITIVE (added back to net income as a non-cash expense)
ITR DFC, same grupo + descricao search
  - Quarterly cumulative at Mar/Jun/Sep 30 (meses=3/6/9)

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 D&A
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 D&A
  DFP 2023 (meses=12)   = full year 2023 D&A
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM D&A computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.da import da_at
    d = da_at("PETR4", "2024-06-30")  # -> 15_000_000_000.0
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# D&A has no single fixed CVM code in the DFC. We search by description.
# `grupo LIKE '%Fluxo de Caixa%'` matches both DFC_MI and DFC_MD statements.
# SQLite LIKE is case-insensitive by default for ASCII, but we wrap descricao
# in LOWER() so accented Portuguese characters (Depreciação) are matched
# case-insensitively too (ASCII substring matches work regardless of accents
# since we only match the un-accented stems 'deprec'/'amort').


def _get_dfp_da(company: str) -> dict[str, dict]:
    """Get all annual D&A from DFP (DFC, descricao search, meses=12).

    SUMs all matching line items per (data_fim_exerc, ano). D&A in the DFC
    is typically POSITIVE (added back to net income as a non-cash expense),
    so we sum raw values without negation.

    Returns: {"2024": {"value": 15e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Keyed by year (string).
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.grupo LIKE '%Fluxo de Caixa%'
                 AND (LOWER(c.descricao) LIKE '%deprec%' OR LOWER(c.descricao) LIKE '%amort%')
                 AND c.meses = 12
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        # Sum all matching line items per (data_fim_exerc, ano)
        # D&A may be split into multiple codes per filer.
        by_period: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            ano = str(r["ano"])
            if ano not in by_period:
                by_period[ano] = {
                    "value": 0.0,
                    "date": r["data_fim_exerc"],
                }
            by_period[ano]["value"] += valor
        return by_period
    finally:
        conn.close()


def _get_itr_da(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative D&A from ITR (DFC, descricao search, meses 3/6/9).

    SUMs all matching line items per data_fim_exerc. Cumulative (Jan->period end).

    Returns: {"2024-06-30": {"value": 7e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied).
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.grupo LIKE '%Fluxo de Caixa%'
                 AND (LOWER(c.descricao) LIKE '%deprec%' OR LOWER(c.descricao) LIKE '%amort%')
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        by_date: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            date = r["data_fim_exerc"]
            if date not in by_date:
                by_date[date] = {
                    "value": 0.0,
                    "meses": r["meses"],
                    "year": r["ano"],
                }
            by_date[date]["value"] += valor
        return by_date
    finally:
        conn.close()


def da_at(company: str, date: str) -> float | None:
    """Get trailing twelve months Depreciação e Amortização ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM D&A in BRL, or None if data not available.
    """
    dfp = _get_dfp_da(company)
    itr = _get_itr_da(company)

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


def da_periods(company: str) -> list[dict]:
    """Get all TTM D&A periods for a company.

    Returns a list of {"date": period_end_date, "ttm_da": value} sorted oldest-first.
    Each entry represents a point where TTM D&A changed (new ITR/DFP filed).

    Useful for building step-function D&A overlays on price charts.
    """
    dfp = _get_dfp_da(company)
    itr = _get_itr_da(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = da_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_da": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_da": data["value"]})

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
    name="da",
    quantity="ttm_da",
    at_fn=da_at,
    periods_fn=da_periods,
    source="DFP + ITR DFC (Depreciação e Amortização by description search, TTM)",
    category="dfc",
))
