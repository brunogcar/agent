"""engines/dva/va_received.py -- TTM (trailing twelve months) DVA VA Received engine.

DVA 7.07 = Vlr Adicionado Recebido em Transferência (VA Received in
Transfer). Wealth received from other entities — typically equity-method
subsidiaries, associates, and joint ventures — that was produced outside
the reporting entity but is now available for distribution. This is the
final addition on the DVA "generation side":

  Total VA to Distribute (7.08) = Net VA Produced (7.06) + VA Received (7.07)

Mirrors engines/dva/revenue.py (DVA 7.01) with:
  - CVM account code 7.07 (VA Recebido em Transferência) instead of 7.01
  - No new-chart equivalent (7.07 is used in both old + new chart formats)

SQL filter: `AND c.grupo LIKE '%Valor Adicionado%' AND c.codigo = '7.07'`
(the grupo filter is required because codigo 7.07 only appears in the DVA
statement, but the grupo column distinguishes DVA rows from DRE/BPA/BPP).

DVA = Demonstração do Valor Adicionado (Value Added Statement). The
generation side shows how wealth is CREATED:
  Revenues (7.01) - Inputs (7.03) = Gross Value Added (7.04)
  + Retentions (7.05) = Net Value Added Produced (7.06)
  + VA Received in Transfer (7.07) = Total VA to Distribute (7.08)

SIGN CONVENTION
---------------
DVA 7.07 (VA Received in Transfer) is typically reported as a POSITIVE
figure (wealth received from subsidiaries/associates increases the total
available for distribution). This engine returns the RAW value from the
database.

CROSS-CHECK
-----------
Total VA to Distribute (7.08, via value_added_at) should approximately
equal va_net_at + va_received_at (7.08 ~= 7.06 + 7.07). Significant
deviations flag accounting inconsistencies between the reported total and
the underlying line items.

TTM ALGORITHM
-------------
For a date D, find the most recent ITR period (data_fim_exerc <= D):

  TTM = DFP_prior_year - ITR_prior_year_same_period + ITR_current_period

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.dva.va_received import va_received_at
    r = va_received_at("PETR4", "2024-06-30")  # -> 2e9 (positive transfer)
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Vlr Adicionado Recebido em Transferência (VA Received
# in Transfer) -- final addition on the DVA generation side:
# 7.08 = 7.06 (Net VA Produced) + 7.07 (VA Received).
VA_VA_RECEIVED_CODE = "7.07"


def _get_dfp_va_received(company: str) -> dict[str, dict]:
    """Get all annual DVA VA received in transfer from DFP (codigo 7.07, meses=12).

    Returns: {"2024": {"value": 2e9, "date": "2024-12-31"}, ...}
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
                 AND c.codigo = ?
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            (*empresa_ids, VA_VA_RECEIVED_CODE),
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


def _get_itr_va_received(company: str) -> dict[str, dict]:
    """Get all quarterly cumulative DVA VA received from ITR (codigo 7.07, meses 3/6/9).

    Returns: {"2024-06-30": {"value": 1e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Cumulative (Jan -> period end).
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
                 AND c.codigo = ?
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            (*empresa_ids, VA_VA_RECEIVED_CODE),
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
def va_received_at(company: str, date: str) -> float | None:
    """Get trailing twelve months DVA VA received in transfer (7.07) ending at or before date.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        TTM DVA VA received in transfer in BRL (typically POSITIVE -- wealth
        received from subsidiaries/associates), or None if data not available
        (company does not file DVA, or insufficient ITR history).
    """
    dfp = _get_dfp_va_received(company)
    itr = _get_itr_va_received(company)

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
def va_received_periods(company: str) -> list[dict]:
    """Get all TTM DVA VA received in transfer (7.07) periods for a company.

    Returns a list of {"date": period_end_date, "ttm_va_received": value}
    sorted oldest-first.
    """
    dfp = _get_dfp_va_received(company)
    itr = _get_itr_va_received(company)

    if not itr and not dfp:
        return []

    all_itr_dates = sorted(itr.keys())
    periods = []

    for itr_date in all_itr_dates:
        ttm = va_received_at(company, itr_date)
        if ttm is not None:
            periods.append({"date": itr_date, "ttm_va_received": ttm})

    for year, data in sorted(dfp.items()):
        if all_itr_dates and data["date"] < all_itr_dates[0]:
            periods.append({"date": data["date"], "ttm_va_received": data["value"]})
        elif not all_itr_dates:
            periods.append({"date": data["date"], "ttm_va_received": data["value"]})

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
    name="va_received",
    quantity="ttm_va_received",
    at_fn=va_received_at,
    periods_fn=va_received_periods,
    source="DFP (annual) + ITR (quarterly cumulative) DVA grupo LIKE '%Valor Adicionado%' codigo 7.07 -- Vlr Adicionado Recebido em Transferência TTM",
    category="dva",
))
