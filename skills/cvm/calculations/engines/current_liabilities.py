"""engines/current_liabilities.py — Passivo Circulante (current liabilities) snapshot engine.

Gets consolidated Passivo Circulante at any historical date from DFP + ITR.

Current liabilities is a SNAPSHOT (point-in-time balance), not a flow. So this
engine is simpler than earnings.py — no TTM derivation. We just find the most
recent BPP snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPP (Balanço Patrimonial Passivo), codigo 2.01 = "Passivo Circulante"
  - The current liabilities section of the balance sheet (obligations due
    within 12 months).
  - Annual snapshot at Dec 31 (meses=12)
ITR BPP, same codigo 2.01
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, current liabilities is
constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Current liabilities snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.current_liabilities import (
        current_liabilities_at, current_liabilities_periods,
    )
    v = current_liabilities_at("PETR4", "2024-06-30")        # → 120e9 (BRL)
    ps = current_liabilities_periods("PETR4")                # → [{date, current_liabilities}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Passivo Circulante Consolidado (BPP group)
PASSIVO_CIRCULANTE_CODE = "2.01"


def _get_dfp_current_liabilities(company: str) -> dict[str, dict]:
    """Get all annual current liabilities snapshots from DFP (codigo 2.01, meses=12, BPP).

    Returns: {"2024-12-31": {"value": 120e9, "year": 2024}, ...}
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
                 AND c.codigo = '{PASSIVO_CIRCULANTE_CODE}'
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


def _get_itr_current_liabilities(company: str) -> dict[str, dict]:
    """Get all quarterly current liabilities snapshots from ITR (codigo 2.01, meses 3/6/9, BPP).

    Returns: {"2024-06-30": {"value": 115e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{PASSIVO_CIRCULANTE_CODE}'
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
def current_liabilities_at(company: str, date: str) -> float | None:
    """Get Passivo Circulante closest to date (most recent snapshot <= date).

    Current liabilities is a point-in-time balance, so we just find the most
    recent BPP snapshot at or before the requested date. No TTM derivation
    needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Current liabilities in BRL, or None if no snapshot available at or
        before date.
    """
    dfp = _get_dfp_current_liabilities(company)
    itr = _get_itr_current_liabilities(company)

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
def current_liabilities_periods(company: str) -> list[dict]:
    """Get all current liabilities snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "current_liabilities": 115e9}, ...]
    Sorted oldest-first. Each entry is a point where current liabilities
    changed (new BPP snapshot filed). Deduplicated by date.

    Useful for building step-function current liabilities overlays on price
    charts.
    """
    dfp = _get_dfp_current_liabilities(company)
    itr = _get_itr_current_liabilities(company)

    # Merge and dedupe by date (ITR takes precedence if same date — same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "current_liabilities": by_date[d]} for d in sorted(by_date.keys())]


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="current_liabilities",
    quantity="current_liabilities",
    at_fn=current_liabilities_at,
    periods_fn=current_liabilities_periods,
    source="DFP + ITR BPP codigo 2.01 (Passivo Circulante snapshot)",
    category="bpp",
))
