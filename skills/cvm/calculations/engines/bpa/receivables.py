"""engines/bpa/receivables.py -- Contas a Receber (receivables) snapshot engine.

Gets consolidated Contas a Receber at any historical date from DFP + ITR.

Receivables is a SNAPSHOT (point-in-time balance), not a flow. So this
engine is simpler than earnings.py -- no TTM derivation. We just find the
most recent BPA snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPA (Balanço Patrimonial Ativo), codigo 1.01.03 = "Contas a Receber"
  - The short-term receivables line within Ativo Circulante (clientes +
    outros créditos a receber dentro de 12 meses).
  - Annual snapshot at Dec 31 (meses=12)
ITR BPA, same codigo 1.01.03
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, receivables are
constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Receivables snapshots computable from: 2010 onwards.

NOTE: codigo 1.01.03 is the consolidated Contas a Receber line WITHIN
Ativo Circulante (codigo 1.01). For total receivables (including
long-term), a separate engine would be needed -- this is the current
(short-term) portion only, which is what most liquidity metrics need.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.bpa.receivables import (
        receivables_at, receivables_periods,
    )
    v = receivables_at("PETR4", "2024-06-30")        # -> 50e9 (BRL)
    ps = receivables_periods("PETR4")                # -> [{date, receivables}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Contas a Receber Consolidado (BPA line within Ativo Circulante)
CONTAS_A_RECEBER_CODE = "1.01.03"


@engine_cached
def _get_dfp_receivables(company: str) -> dict[str, dict]:
    """Get all annual receivables snapshots from DFP (codigo 1.01.03, meses=12, BPA).

    Returns: {"2024-12-31": {"value": 50e9, "year": 2024}, ...}
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
                 AND c.codigo = '{CONTAS_A_RECEBER_CODE}'
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


@engine_cached
def _get_itr_receivables(company: str) -> dict[str, dict]:
    """Get all quarterly receivables snapshots from ITR (codigo 1.01.03, meses 3/6/9, BPA).

    Returns: {"2024-06-30": {"value": 48e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{CONTAS_A_RECEBER_CODE}'
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
def receivables_at(company: str, date: str) -> float | None:
    """Get Contas a Receber closest to date (most recent snapshot <= date).

    Receivables is a point-in-time balance, so we just find the most
    recent BPA snapshot at or before the requested date. No TTM derivation
    needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Receivables in BRL, or None if no snapshot available at or before date.
    """
    dfp = _get_dfp_receivables(company)
    itr = _get_itr_receivables(company)

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


@engine_cached
def receivables_periods(company: str) -> list[dict]:
    """Get all receivables snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "receivables": 48e9}, ...]
    Sorted oldest-first. Each entry is a point where receivables changed
    (new BPA snapshot filed). Deduplicated by date.

    Useful for building step-function receivables overlays on price charts.
    """
    dfp = _get_dfp_receivables(company)
    itr = _get_itr_receivables(company)

    # Merge and dedupe by date (ITR takes precedence if same date -- same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "receivables": by_date[d]} for d in sorted(by_date.keys())]


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402
register_engine(EngineSpec(
    name="receivables",
    quantity="receivables",
    at_fn=receivables_at,
    periods_fn=receivables_periods,
    source="DFP + ITR BPA codigo 1.01.03 (Contas a Receber snapshot)",
    category="bpa",
))
