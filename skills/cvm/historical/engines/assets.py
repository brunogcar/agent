"""engines/assets.py — Ativo Total (total assets) snapshot engine.

Gets consolidated Ativo Total at any historical date from DFP + ITR.

Assets is a SNAPSHOT (point-in-time balance), not a flow. So this engine is
simpler than earnings.py — no TTM derivation. We just find the most recent
BPA snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPA (Balanço Patrimonial Ativo), codigo 1.01 = "Ativo Total"
  - Annual snapshot at Dec 31 (meses=12)
ITR BPA, same codigo 1.01
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, assets is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Assets snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.engines.assets import assets_at, assets_periods
    v = assets_at("PETR4", "2024-06-30")        # → 380e9 (BRL)
    ps = assets_periods("PETR4")                # → [{date, assets}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for Ativo Total Consolidado (BPA group)
ATIVO_TOTAL_CODE = "1.01"


def _get_dfp_assets(company: str) -> dict[str, dict]:
    """Get all annual assets snapshots from DFP (codigo 1.01, meses=12, BPA).

    Returns: {"2024-12-31": {"value": 380e9, "year": 2024}, ...}
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
                 AND c.codigo = '{ATIVO_TOTAL_CODE}'
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


def _get_itr_assets(company: str) -> dict[str, dict]:
    """Get all quarterly assets snapshots from ITR (codigo 1.01, meses 3/6/9, BPA).

    Returns: {"2024-06-30": {"value": 375e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{ATIVO_TOTAL_CODE}'
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


def assets_at(company: str, date: str) -> float | None:
    """Get Ativo Total closest to date (most recent snapshot <= date).

    Assets is a point-in-time balance, so we just find the most recent BPA
    snapshot at or before the requested date. No TTM derivation needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Assets in BRL, or None if no snapshot available at or before date.
    """
    dfp = _get_dfp_assets(company)
    itr = _get_itr_assets(company)

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


def assets_periods(company: str) -> list[dict]:
    """Get all assets snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "assets": 375e9}, ...]
    Sorted oldest-first. Each entry is a point where assets changed
    (new BPA snapshot filed). Deduplicated by date.

    Useful for building step-function assets overlays on price charts.
    """
    dfp = _get_dfp_assets(company)
    itr = _get_itr_assets(company)

    # Merge and dedupe by date (ITR takes precedence if same date — same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "assets": by_date[d]} for d in sorted(by_date.keys())]


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.historical._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="assets",
    quantity="assets",
    at_fn=assets_at,
    periods_fn=assets_periods,
    source="DFP + ITR BPA codigo 1.01 (Ativo Total snapshot)",
    category="bpa",
))
