"""engines/pl.py — Patrimônio Líquido (equity) snapshot engine.

Gets consolidated Patrimônio Líquido at any historical date from DFP + ITR.

PL is a SNAPSHOT (point-in-time balance), not a flow. So this engine is
simpler than earnings.py — no TTM derivation. We just find the most recent
BPP snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPP (Balanço Patrimonial Passivo), codigo 2.03 = "Patrimônio Líquido"
  - Annual snapshot at Dec 31 (meses=12)
ITR BPP, same codigo 2.03
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, PL is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
PL snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.historical.engines.pl import pl_at, pl_periods
    v = pl_at("PETR4", "2024-06-30")        # → 380e9 (BRL)
    ps = pl_periods("PETR4")                # → [{date, pl}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for Patrimônio Líquido Consolidado (BPP group)
PATRIMONIO_LIQUIDO_CODE = "2.03"


def _get_dfp_pl(company: str) -> dict[str, dict]:
    """Get all annual PL snapshots from DFP (codigo 2.03, meses=12, BPP).

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
                 AND c.codigo = '{PATRIMONIO_LIQUIDO_CODE}'
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


def _get_itr_pl(company: str) -> dict[str, dict]:
    """Get all quarterly PL snapshots from ITR (codigo 2.03, meses 3/6/9, BPP).

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
                 AND c.codigo = '{PATRIMONIO_LIQUIDO_CODE}'
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


def pl_at(company: str, date: str) -> float | None:
    """Get Patrimônio Líquido closest to date (most recent snapshot <= date).

    PL is a point-in-time balance, so we just find the most recent BPP
    snapshot at or before the requested date. No TTM derivation needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        PL in BRL, or None if no snapshot available at or before date.
    """
    dfp = _get_dfp_pl(company)
    itr = _get_itr_pl(company)

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


def pl_periods(company: str) -> list[dict]:
    """Get all PL snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "pl": 375e9}, ...]
    Sorted oldest-first. Each entry is a point where PL changed
    (new BPP snapshot filed). Deduplicated by date.

    Useful for building step-function PL overlays on price charts.
    """
    dfp = _get_dfp_pl(company)
    itr = _get_itr_pl(company)

    # Merge and dedupe by date (ITR takes precedence if same date — same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "pl": by_date[d]} for d in sorted(by_date.keys())]


# ── Register with the engine registry ────────────────────────────────────────

from skills.cvm.historical._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="pl",
    quantity="pl",
    at_fn=pl_at,
    periods_fn=pl_periods,
    source="DFP + ITR BPP codigo 2.03 (Patrimônio Líquido snapshot)",
    category="bpp",
))
