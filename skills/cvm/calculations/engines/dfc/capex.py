"""engines/dfc/capex.py -- TTM (trailing twelve months) CapEx engine.

CapEx (Capital Expenditure) has no single standardized CVM account code in
the DFC. Different filers report it under varying line items, typically
described as "Aquisição de Imobilizado", "Aquisição de Ativos Imobilizados",
"Aquisição de Intangível", "Aquisição de Ativos Intangíveis", etc. To handle
this, we:

  1. Search by DESCRIPTION, not by codigo: descricao LIKE '%imobilizado%' OR
     descricao LIKE '%intangivel%' (case-insensitive).
  2. SUM all matching line items per period (there may be multiple).
  3. Apply TTM derivation (CapEx is a flow, like D&A / revenue).

DATA SOURCE
-----------
DFP DFC (Demonstração do Fluxo de Caixa), grupo LIKE '%Fluxo de Caixa%'
  - Matches both DFC_MI (Método Indireto) and DFC_MD (Método Direto)
  - Annual flow at Dec 31 (meses=12)
  - CapEx is typically NEGATIVE (cash outflow for asset purchases)
ITR DFC, same grupo + descricao search
  - Quarterly cumulative at Mar/Jun/Sep 30 (meses=3/6/9)

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Example for D = 2024-08-15 (most recent ITR = Q2 2024, data_fim = 2024-06-30):
  ITR 2024 Q2 (meses=6) = cumulative H1 2024 CapEx
  ITR 2023 Q2 (meses=6) = cumulative H1 2023 CapEx
  DFP 2023 (meses=12)   = full year 2023 CapEx
  TTM = DFP_2023 - ITR_2023_H1 + ITR_2024_H1 = 12 months ending 2024-06-30

DATA RANGE
----------
DFP: 2010-present (annual, meses=12)
ITR: 2011-present (quarterly cumulative, meses=3/6/9)
TTM CapEx computable from: ~2012 onwards (need 2 years of ITR)

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dfc.capex import capex_at
    v = capex_at("PETR4", "2024-06-30")  # -> -15_000_000_000.0 (negative outflow)
"""

from __future__ import annotations

import unicodedata

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CapEx has no single fixed CVM code in the DFC. We search by description.
# `grupo LIKE '%Fluxo de Caixa%'` matches both DFC_MI and DFC_MD statements.
# SQLite LIKE is case-insensitive by default for ASCII, but we wrap descricao
# in LOWER() so accented Portuguese characters (Imobilizado) are matched
# case-insensitively too (ASCII substring matches work regardless of accents
# since we only match the un-accented stems 'imobilizado'/'intangivel').
#
# SECTION SCOPING (v1.1 fix):
# The broad `grupo LIKE '%Fluxo de Caixa%'` filter matches the ENTIRE DFC
# statement (operating + investing + financing sections).  The keyword
# 'imobilizado' alone would also match "Baixa de Imobilizado" — a
# non-cash reconciling line in the OPERATING section (codigo 6.01.xx),
# not the actual capex outflow which lives in the INVESTING section
# (codigo 6.02.xx, typically "Aquisição de Imobilizado").  Different sign
# convention, different section — silently mixing them corrupts the sum.
# Fix: scope to the investing section via `codigo LIKE '6.02.%'`, plus a
# Python-side accent-normalized exclusion for 'baixa' (disposal/write-off)
# as defense-in-depth.

CAPEX_KEYWORDS = ("imobilizado", "intangivel")

# Accent-normalized negative keywords — descriptions containing these stems
# are disposal/write-off or non-cash reconciling lines, NOT capex outflows.
_CAPEX_EXCLUDE_STEMS = ("baixa", "alienacao", "despesa")


def _strip_accents(s: str) -> str:
    """Remove diacritics from a Portuguese string (e.g. 'Alienação' -> 'Alienacao').

    SQLite LOWER() only lowercases ASCII; it does NOT strip accents.  We do
    the accent-stripping in Python where unicodedata is available so 'Alienação'
    is caught regardless of accent.
    """
    if not s:
        return ""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )


def _is_disposal_line(descricao: str) -> bool:
    """True if a DFC line description is a disposal/write-off, not capex.

    Accent-normalized so 'Alienação de Imobilizado' is caught.
    """
    norm = _strip_accents(descricao).lower()
    return any(stem in norm for stem in _CAPEX_EXCLUDE_STEMS)


def _build_desc_filter(column: str = "c.descricao") -> str:
    """Build a SQL OR-clause matching any CAPEX_KEYWORDS as a substring.

    Returns e.g.: "LOWER(c.descricao) LIKE '%imobilizado%' OR LOWER(c.descricao) LIKE '%intangivel%'"
    """
    return " OR ".join(
        f"LOWER({column}) LIKE '%{kw}%'" for kw in CAPEX_KEYWORDS
    )


@engine_cached
def _get_dfp_capex(company: str) -> dict[str, dict]:
    """Get all annual CapEx from DFP (DFC, descricao search, meses=12).

    SUMs all matching line items per (data_fim_exerc, ano). CapEx in the DFC
    is typically NEGATIVE (cash outflow for asset purchases), so we sum raw
    values without negation — callers should expect a negative number.

    Returns: {"2024": {"value": -15e9, "date": "2024-12-31"}, ...}
    Values are in BRL (escala applied). Keyed by year (string).
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_filter = _build_desc_filter()
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.grupo LIKE '%Fluxo de Caixa%'
                 AND c.codigo LIKE '6.02.%'
                 AND ({desc_filter})
                 AND c.meses = 12
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        # Sum all matching line items per (data_fim_exerc, ano)
        # CapEx may be split into multiple codes per filer.
        # Exclude disposal/write-off lines (e.g. 'Baixa de Imobilizado') that
        # slip through the 'imobilizado' keyword match despite the 6.02.codigo
        # scope — defense-in-depth for any edge-case filer.
        by_period: dict[str, dict] = {}
        for r in rows:
            if _is_disposal_line(r["descricao"] or ""):
                continue
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


@engine_cached
def _get_itr_capex(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative CapEx from ITR (DFC, descricao search, meses 3/6/9).

    SUMs all matching line items per data_fim_exerc. Cumulative (Jan->period end).
    Values are typically NEGATIVE (cash outflow).

    Returns: {"2024-06-30": {"value": -7e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied).
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        desc_filter = _build_desc_filter()
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, e.ano, c.descricao
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.grupo LIKE '%Fluxo de Caixa%'
                 AND c.codigo LIKE '6.02.%'
                 AND ({desc_filter})
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        by_date: dict[str, dict] = {}
        for r in rows:
            if _is_disposal_line(r["descricao"] or ""):
                continue
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


@engine_cached
def capex_at(company: str, date: str) -> float | None:
    """Get trailing twelve months CapEx ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM CapEx in BRL (typically negative — cash outflow), or None if
        data not available.
    """
    dfp = _get_dfp_capex(company)
    itr = _get_itr_capex(company)

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

    # [v2.5 fix B31] When the current year's DFP (full year, meses=12) is
    # available and its date <= the query date, return the full-year DFP
    # value directly. This handles the case where the user queries
    # date=2024-12-31 (year-end) but the most recent ITR is 2024-09-30
    # (Q3). Without this, the TTM would end at 2024-09-30 (stale by one
    # quarter). The DFP for the current year IS the full-year CapEx, so
    # returning it directly is the correct year-end value.
    current_dfp = dfp.get(str(current_year))
    if current_dfp and current_dfp["date"] <= date:
        return current_dfp["value"]

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
def capex_periods(company: str) -> list[dict]:
    """Get all TTM CapEx periods for a company.

    Returns a list of {"date": period_end_date, "ttm_capex": value} sorted oldest-first.
    Each entry represents a point where TTM CapEx changed (new ITR/DFP filed).

    Useful for building step-function CapEx overlays on price charts.
    """
    dfp = _get_dfp_capex(company)
    itr = _get_itr_capex(company)

    if not itr and not dfp:
        return []

    # Build all ITR periods sorted oldest-first
    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = capex_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_capex": ttm})

    # Also add DFP-only periods (for years before ITR data)
    for year, data in sorted(dfp.items()):
        if data["date"] < all_itr_dates[0] if all_itr_dates else True:
            periods.append({"date": data["date"], "ttm_capex": data["value"]})

    # [v2.5 fix B30] Also add the latest DFP date when it's more recent than
    # the latest ITR. Without this, the most recent annual period (e.g.
    # 2024-12-31 DFP after the latest ITR 2024-09-30) is missing from the
    # result, so the annual comprehensive table's most recent year falls
    # back to the FCI proxy instead of real CapEx.
    if dfp and all_itr_dates:
        latest_dfp_year = max(dfp.keys())
        latest_dfp = dfp[latest_dfp_year]
        if latest_dfp["date"] > all_itr_dates[-1]:
            # capex_at for the DFP date returns full-year CapEx when the DFP
            # is available (the B31 fix in capex_at handles this).
            full_year_capex = capex_at(company, latest_dfp["date"])
            if full_year_capex is not None:
                periods.append({"date": latest_dfp["date"],
                                "ttm_capex": full_year_capex})

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
    name="capex",
    quantity="ttm_capex",
    at_fn=capex_at,
    periods_fn=capex_periods,
    source="DFP + ITR DFC (CapEx by description search: imobilizado/intangivel, TTM)",
    category="dfc",
))
