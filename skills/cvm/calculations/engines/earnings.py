"""engines/earnings.py — TTM (trailing twelve months) earnings engine.

The core innovation of the historical skill. Derives TTM earnings at any
historical date by combining DFP annual + ITR quarterly cumulative data.

DESCRIPTION-SEARCH FALLBACK
---------------------------
For commercial/industrial filers, codigo 3.11 is "Lucro Líquido do Período".
For financial-sector filers (banks/insurers), however, the DRE template
uses a different bottom-line label like "Lucro do Período" or "Resultado
Líquido Consolidado", and may shift the position to a different 3.* slot.
The reference implementation (rapinav2) handles this with a wildcard +
mandatory description match: codigo '3.*' + descricao LIKE '%Lucro
Liquido%' (or '%Lucro do Periodo%' / '%Resultado Líquido Consolidado%').
We mirror that approach as a FALLBACK: the fast path tries the exact 3.11
code (works for the vast majority of filers and is O(1) on the codigo
index), and only if that returns nothing do we fall back to the
description search within the 3.* DRE range.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 earnings
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 earnings
  DFP 2023 (meses=12)   = full year 2023 earnings
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM earnings computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.earnings import ttm_earnings_at
    e = ttm_earnings_at("PETR4", "2024-06-30")  # → 134000000000.0
"""

from __future__ import annotations

from typing import Any

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for net income (lucro líquido). Standard position in the
# DRE for commercial/industrial filers. Banks/insurers use a different DRE
# template (their bottom-line may be labeled "Lucro do Período" or
# "Resultado Líquido Consolidado" at a different 3.* position), so we fall
# back to a description-based search within the 3.* DRE range when 3.11
# returns nothing.
LUCRO_LIQUIDO_CODE = "3.11"

# Description stems used for the fallback search.  We match on partial
# stems (not the full string) so minor wording variations across filers
# are caught.  Banks/insurers may use "Lucro do Periodo" or
# "Resultado Líquido Consolidado" instead of "Lucro Liquido".
_EARNINGS_DESC_STEMS = (
    "Lucro Liquido",
    "Lucro do Periodo",
    "Resultado Liquido Consolidado",
)


def _get_dfp_earnings(company: str) -> dict[str, dict]:
    """Get all annual earnings from DFP (codigo 3.11, meses=12).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.11 code returns nothing -- handles banks/insurers whose
    DRE structure uses "Lucro do Período" or "Resultado Líquido Consolidado"
    instead of "Lucro Líquido".

    Returns: {"2024": {"value": 134e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied).
    """
    result = _get_dfp_earnings_by_code(company, LUCRO_LIQUIDO_CODE)
    if result:
        return result
    # Fallback: description search within DRE (3.*) for filers where 3.11
    # doesn't land on net income (banks/insurers, non-standard DRE filers).
    return _get_dfp_earnings_by_desc(company)


def _get_dfp_earnings_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.11). Returns {} if nothing found."""
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


def _get_dfp_earnings_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by earnings description stems.

    Used when the exact 3.11 code doesn't match (banks/insurers, non-standard
    DRE filers). Mirrors rapinav2's wildcard + description-match approach.
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _EARNINGS_DESC_STEMS
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


def _get_itr_earnings(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative earnings from ITR (codigo 3.11, meses 3/6/9).

    Falls back to a description-based search within the DRE (codigo LIKE '3.%')
    if the exact 3.11 code returns nothing -- mirrors the DFP fallback.

    Returns: {"2024-06-30": {"value": 67e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan→period end).
    """
    result = _get_itr_earnings_by_code(company, LUCRO_LIQUIDO_CODE)
    if result:
        return result
    return _get_itr_earnings_by_desc(company)


def _get_itr_earnings_by_code(company: str, code: str) -> dict[str, dict]:
    """Fast path: exact codigo match (3.11). Returns {} if nothing found."""
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


def _get_itr_earnings_by_desc(company: str) -> dict[str, dict]:
    """Fallback: search DRE (codigo LIKE '3.%') by earnings description stems."""
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_clause = " OR ".join(
            f"c.descricao LIKE '%{stem}%'" for stem in _EARNINGS_DESC_STEMS
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
def ttm_earnings_at(company: str, date: str) -> float | None:
    """Get trailing twelve months earnings ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM earnings in BRL, or None if data not available.
    """
    dfp = _get_dfp_earnings(company)
    itr = _get_itr_earnings(company)

    if not itr and not dfp:
        return None

    # Find the most recent ITR period <= date
    itr_dates = sorted([d for d in itr.keys() if d <= date], reverse=True)
    if not itr_dates:
        # No ITR data before this date — try DFP annual
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
        # No ITR for prior year same period — use DFP directly as approximation
        return prior_dfp["value"]
    elif current and not prior_dfp:
        # No DFP for prior year — can't derive TTM
        return None
    else:
        return None


@engine_cached
def ttm_earnings_periods(company: str) -> list[dict]:
    """Get all TTM earnings periods for a company.

    Returns a list of {"date": period_end_date, "ttm": value} sorted oldest-first.
    Each entry represents a point where TTM earnings changed (new ITR/DFP filed).

    Useful for building step-function earnings overlays on price charts.
    """
    dfp = _get_dfp_earnings(company)
    itr = _get_itr_earnings(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = ttm_earnings_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm": data["value"]})

    # Sort and deduplicate by date
    periods.sort(key=lambda p: p["date"])
    seen = set()
    result = []
    for p in periods:
        if p["date"] not in seen:
            result.append(p)
            seen.add(p["date"])

    return result


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="earnings",
    quantity="ttm",
    at_fn=ttm_earnings_at,
    periods_fn=ttm_earnings_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DRE 3.11 — TTM derivation (with description-search fallback for non-standard filers)",
    category="dre",
))
