"""engines/dre/ebit.py -- TTM (trailing twelve months) EBIT engine.

Mirrors engines/dre/revenue.py with one change: CVM account code 3.05
(EBIT / Resultado Antes do Resultado Financeiro e dos Tributos) instead
of 3.01 (Receita Liquida). The TTM derivation algorithm is identical.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 EBIT
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 EBIT
  DFP 2023 (meses=12)   = full year 2023 EBIT
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM EBIT computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dre.ebit import ebit_at
    r = ebit_at("PETR4", "2024-06-30")  # -> 280000000000.0
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for EBIT (Resultado Antes do Resultado Financeiro e dos Tributos).
# This is the standard position in the DRE for commercial/industrial filers.
# However, EBIT's position can shift for filers with extra revenue/expense
# line breakdowns (more granular filers push EBIT to 3.06 or 3.07), and
# financial-sector filers (banks/insurers) use a completely different DRE
# template that doesn't follow the commercial 3.01-3.11 chart at all.
#
# The reference implementation (rapinav2) handles this with a wildcard +
# mandatory description match: codigo '3.*' + descricao 'Resultado Antes do
# Resultado Financeiro e dos Tributos'.  We mirror that approach as a FALLBACK:
# the fast path tries the exact 3.05 code (works for the vast majority of
# filers and is O(1) on the codigo index), and only if that returns nothing
# do we fall back to the description search within the 3.* DRE range.
EBIT_CODE = "3.05"

# Description stems used for the fallback search.  We match on a partial stem
# (not the full string) so minor wording variations across filers are caught.
_EBIT_DESC_STEMS = (
    "Resultado Antes do Resultado Financeiro",
    "Resultado Antes Dos Resultados Financeiros",  # plural variant
)


@engine_cached
def _get_dfp_ebit(company: str) -> dict[str, dict]:
    """Get all annual EBIT from DFP (codigo 3.05, meses=12).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.05 code returns nothing — handles filers whose DRE structure
    shifts EBIT to a different position (e.g. banks, insurers, or filers with
    extra line-item breakdowns).

    Returns: {"2024": {"value": 280e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied).
    """
    result = _get_dfp_ebit_by_code(company, EBIT_CODE)
    if result:
        return result
    # Fallback: description search within DRE (3.*) for filers where 3.05
    # doesn't land on EBIT (non-standard DRE structure).
    return _get_dfp_ebit_by_desc(company)


@engine_cached
def _get_dfp_ebit_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.05). Returns {} if nothing found."""
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
def _get_dfp_ebit_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by EBIT description stems.

    Used when the exact 3.05 code doesn't match (non-standard DRE filers).
    Mirrors rapinav2's wildcard + description-match approach.
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _EBIT_DESC_STEMS
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

        # If multiple rows match per year (shouldn't happen, but defensive),
        # take the first (most recent descricao match).
        result = {}
        for r in rows:
            ano = str(r["ano"])
            if ano in result:
                continue
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            result[ano] = {
                "value": valor,
                "date": r["data_fim_exerc"],
            }
        return result
    finally:
        conn.close()


@engine_cached
def _get_itr_ebit(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative EBIT from ITR (codigo 3.05, meses 3/6/9).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.05 code returns nothing — mirrors the DFP fallback.

    Returns: {"2024-06-30": {"value": 140e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan->period end).
    """
    result = _get_itr_ebit_by_code(company, EBIT_CODE)
    if result:
        return result
    return _get_itr_ebit_by_desc(company)


@engine_cached
def _get_itr_ebit_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.05). Returns {} if nothing found."""
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
def _get_itr_ebit_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by EBIT description stems."""
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _EBIT_DESC_STEMS
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

        # If multiple rows match per period (shouldn't happen), take the first.
        result = {}
        for r in rows:
            date = r["data_fim_exerc"]
            if date in result:
                continue
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            result[date] = {
                "value": valor,
                "meses": r["meses"],
                "year": r["ano"],
            }
        return result
    finally:
        conn.close()


@engine_cached
def ebit_at(company: str, date: str) -> float | None:
    """Get trailing twelve months EBIT ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM EBIT in BRL, or None if data not available.
    """
    dfp = _get_dfp_ebit(company)
    itr = _get_itr_ebit(company)

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
def ebit_periods(company: str) -> list[dict]:
    """Get all TTM EBIT periods for a company.

    Returns a list of {"date": period_end_date, "ttm_ebit": value} sorted oldest-first.
    Each entry represents a point where TTM EBIT changed (new ITR/DFP filed).

    Useful for building step-function EBIT overlays on price charts.
    """
    dfp = _get_dfp_ebit(company)
    itr = _get_itr_ebit(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = ebit_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_ebit": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_ebit": data["value"]})

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
    name="ebit",
    quantity="ttm_ebit",
    at_fn=ebit_at,
    periods_fn=ebit_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DRE 3.05 -- EBIT TTM (with description-search fallback for non-standard filers)",
    category="dre",
))
