"""engines/intangibles.py -- Intangível (intangibles) snapshot engine.

Gets consolidated Intangível at any historical date from DFP + ITR.

Intangibles is a SNAPSHOT (point-in-time balance), not a flow. So this
engine is simpler than earnings.py -- no TTM derivation. We just find the
most recent BPA snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPA (Balanço Patrimonial Ativo), codigo 1.02.04 = "Intangível"
  - Net intangible assets (goodwill, software, trademarks, patents, etc.)
    net of amortization, within Ativo Não Circulante (codigo 1.02).
  - Annual snapshot at Dec 31 (meses=12)
ITR BPA, same codigo 1.02.04
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, intangibles is
constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Intangibles snapshots computable from: 2010 onwards.

NOTE: codigo 1.02.04 is Intangível Líquido (net of amortization). This is
the line item added to the BPA in 2010 when CVM adopted IFRS — goodwill
from acquisitions lives here. Companies with no M&A history often have a
zero or absent line; the engine returns None in that case.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.intangibles import (
        intangibles_at, intangibles_periods,
    )
    v = intangibles_at("PETR4", "2024-06-30")        # -> 60e9 (BRL)
    ps = intangibles_periods("PETR4")                # -> [{date, intangibles}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for Intangível Consolidado (BPA line within Ativo Não Circulante)
INTANGIVEL_CODE = "1.02.04"


def _get_dfp_intangibles(company: str) -> dict[str, dict]:
    """Get all annual intangibles snapshots from DFP (codigo 1.02.04, meses=12, BPA).

    Returns: {"2024-12-31": {"value": 60e9, "year": 2024}, ...}
    Values are in BRL (escala applied).
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
                 AND c.codigo = '{INTANGIVEL_CODE}'
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            empresa_ids,
        ).fetchall()

        result = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            result[r["data_fim_exerc"]] = {
                "value": valor,
                "year": r["ano"],
            }
        return result
    finally:
        conn.close()


def _get_itr_intangibles(company: str) -> dict[str, dict]:
    """Get all quarterly intangibles snapshots from ITR (codigo 1.02.04, meses 3/6/9, BPA).

    Returns: {"2024-06-30": {"value": 58e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied).
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
                 AND c.codigo = '{INTANGIVEL_CODE}'
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


def intangibles_at(company: str, date: str) -> float | None:
    """Get Intangível closest to date (most recent snapshot <= date).

    Intangibles is a point-in-time balance, so we just find the most
    recent BPA snapshot at or before the requested date. No TTM
    derivation needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Intangibles (net book value) in BRL, or None if no snapshot
        available at or before date.
    """
    dfp = _get_dfp_intangibles(company)
    itr = _get_itr_intangibles(company)

    # Merge all snapshots (DFP + ITR), find most recent <= date
    all_dates = sorted(
        [d for d in dfp.keys() if d <= date] + [d for d in itr.keys() if d <= date],
        reverse=True,
    )
    if not all_dates:
        return None

    latest = all_dates[0]
    if latest in itr:
        return itr[latest]["value"]
    return dfp[latest]["value"]


def intangibles_periods(company: str) -> list[dict]:
    """Get all intangibles snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "intangibles": 58e9}, ...]
    Sorted oldest-first. Each entry is a point where intangibles changed
    (new BPA snapshot filed). Deduplicated by date.

    Useful for building step-function intangibles overlays on price charts.
    """
    dfp = _get_dfp_intangibles(company)
    itr = _get_itr_intangibles(company)

    # Merge and dedupe by date (ITR takes precedence if same date -- same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "intangibles": by_date[d]} for d in sorted(by_date.keys())]


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="intangibles",
    quantity="intangibles",
    at_fn=intangibles_at,
    periods_fn=intangibles_periods,
    source="DFP + ITR BPA codigo 1.02.04 (Intangível snapshot)",
    category="bpa",
))
