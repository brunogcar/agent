"""engines/bpa/cash.py — Caixa e Equivalentes de Caixa (cash and cash equivalents) snapshot engine.

Gets consolidated cash and cash equivalents at any historical date from DFP + ITR.

Cash is a SNAPSHOT (point-in-time balance), not a flow. So this engine is
simpler than earnings.py — no TTM derivation. We just find the most recent
BPA snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPA (Balanço Patrimonial Ativo), codigo 1.01.01 = "Caixa e Equivalentes de Caixa"
  - Annual snapshot at Dec 31 (meses=12)
ITR BPA, same codigo 1.01.01
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, cash is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Cash snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.bpa.cash import cash_at, cash_periods
    v = cash_at("PETR4", "2024-06-30")        # → 80e9 (BRL)
    ps = cash_periods("PETR4")                # → [{date, cash}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Caixa e Equivalentes de Caixa Consolidado (BPA group)
CAIXA_CODE = "1.01.01"


@engine_cached
def _get_dfp_cash(company: str) -> dict[str, dict]:
    """Get all annual cash snapshots from DFP (codigo 1.01.01, meses=12, BPA).

    Returns: {"2024-12-31": {"value": 80e9, "year": 2024}, ...}
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
                 AND c.codigo = '{CAIXA_CODE}'
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
def _get_itr_cash(company: str) -> dict[str, dict]:
    """Get all quarterly cash snapshots from ITR (codigo 1.01.01, meses 3/6/9, BPA).

    Returns: {"2024-06-30": {"value": 75e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{CAIXA_CODE}'
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
def cash_at(company: str, date: str) -> float | None:
    """Get Caixa e Equivalentes de Caixa closest to date (most recent snapshot <= date).

    Cash is a point-in-time balance, so we just find the most recent BPA
    snapshot at or before the requested date. No TTM derivation needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Cash and cash equivalents in BRL, or None if no snapshot available at or before date.
    """
    dfp = _get_dfp_cash(company)
    itr = _get_itr_cash(company)

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
def cash_periods(company: str) -> list[dict]:
    """Get all cash snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "cash": 75e9}, ...]
    Sorted oldest-first. Each entry is a point where cash changed
    (new BPA snapshot filed). Deduplicated by date.

    Useful for building step-function cash overlays on price charts.
    """
    dfp = _get_dfp_cash(company)
    itr = _get_itr_cash(company)

    # Merge and dedupe by date (ITR takes precedence if same date — same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "cash": by_date[d]} for d in sorted(by_date.keys())]


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="cash",
    quantity="cash",
    at_fn=cash_at,
    periods_fn=cash_periods,
    source="DFP + ITR BPA codigo 1.01.01 (Caixa e Equivalentes de Caixa snapshot)",
    category="bpa",
))
