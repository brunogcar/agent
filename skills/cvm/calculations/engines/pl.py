"""engines/pl.py — Patrimônio Líquido (equity) snapshot engine.

Gets consolidated Patrimônio Líquido at any historical date from DFP + ITR.

PL is a SNAPSHOT (point-in-time balance), not a flow. So this engine is
simpler than earnings.py — no TTM derivation. We just find the most recent
BPP snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPP (Balanço Patrimonial Passivo):
  - OLD chart (95% of filers): codigo 2.03 = "Patrimônio Líquido"
  - NEW chart (5% of filers): codigo 2.03 = amortized-cost debt (NOT PL!),
    and PL moves to codigo 2.08 = "Patrimônio Líquido Consolidado".
  We query BOTH codes and prefer 2.08 when it exists for a period
  (NEW-chart filers); otherwise fall back to 2.03 (OLD-chart filers).
  Annual snapshot at Dec 31 (meses=12).
ITR BPP, same codigo 2.03 + 2.08 fallback:
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, PL is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
PL snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.pl import pl_at, pl_periods
    v = pl_at("PETR4", "2024-06-30")        # → 380e9 (BRL)
    ps = pl_periods("PETR4")                # → [{date, pl}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account code for Patrimônio Líquido Consolidado (BPP group).
# OLD chart (95% of filers — 6352/6681 rows): 2.03 = "Patrimônio Líquido".
# NEW chart (5% of filers): 2.03 = amortized-cost debt (NOT PL!);
# 2.08 = "Patrimônio Líquido Consolidado" (PL moves here).
# Query BOTH codes; prefer 2.08 when present (NEW-chart filer), otherwise
# fall back to 2.03 (OLD-chart filer).
PATRIMONIO_LIQUIDO_CODE = "2.03"
PATRIMONIO_LIQUIDO_CODE_NEW = "2.08"


def _pick_pl_value(rows_for_period) -> float | None:
    """Pick the correct PL value for a single period from candidate rows.

    Args:
        rows_for_period: iterable of (codigo, valor) tuples for one date.
            May contain 2.03, 2.08, or both.

    Returns:
        PL value, preferring 2.08 (NEW chart) over 2.03 (OLD chart) when
        both exist. Returns None if neither code is present.
    """
    values_by_code = {codigo: valor for codigo, valor in rows_for_period}
    if PATRIMONIO_LIQUIDO_CODE_NEW in values_by_code:
        return values_by_code[PATRIMONIO_LIQUIDO_CODE_NEW]
    return values_by_code.get(PATRIMONIO_LIQUIDO_CODE)


def _get_dfp_pl(company: str) -> dict[str, dict]:
    """Get all annual PL snapshots from DFP (codigo 2.03 + 2.08 fallback, meses=12, BPP).

    Returns: {"2024-12-31": {"value": 380e9, "year": 2024}, ...}
    Values are in BRL (escala applied).

    For each period, prefers 2.08 (NEW chart, 5% of filers) over 2.03 (OLD
    chart, 95% of filers) when both are present.
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.codigo, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ('{PATRIMONIO_LIQUIDO_CODE}', '{PATRIMONIO_LIQUIDO_CODE_NEW}')
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            empresa_ids,
        ).fetchall()

        # Group by date, then pick 2.08 over 2.03 per period.
        rows_by_date: dict[str, list[tuple[str, float]]] = {}
        meta_by_date: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            date_key = r["data_fim_exerc"]
            rows_by_date.setdefault(date_key, []).append((r["codigo"], valor))
            meta_by_date[date_key] = {"year": r["ano"]}

        result = {}
        for date_key, candidates in rows_by_date.items():
            pl_value = _pick_pl_value(candidates)
            if pl_value is not None:
                result[date_key] = {"value": pl_value, **meta_by_date[date_key]}
        return result
    finally:
        conn.close()


def _get_itr_pl(company: str) -> dict[str, dict]:
    """Get all quarterly PL snapshots from ITR (codigo 2.03 + 2.08 fallback, meses 3/6/9, BPP).

    Returns: {"2024-06-30": {"value": 375e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied).

    For each period, prefers 2.08 (NEW chart, 5% of filers) over 2.03 (OLD
    chart, 95% of filers) when both are present.
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, c.codigo, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ('{PATRIMONIO_LIQUIDO_CODE}', '{PATRIMONIO_LIQUIDO_CODE_NEW}')
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        # Group by date, then pick 2.08 over 2.03 per period.
        rows_by_date: dict[str, list[tuple[str, float]]] = {}
        meta_by_date: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            date_key = r["data_fim_exerc"]
            rows_by_date.setdefault(date_key, []).append((r["codigo"], valor))
            meta_by_date[date_key] = {"meses": r["meses"], "year": r["ano"]}

        result = {}
        for date_key, candidates in rows_by_date.items():
            pl_value = _pick_pl_value(candidates)
            if pl_value is not None:
                result[date_key] = {"value": pl_value, **meta_by_date[date_key]}
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

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="pl",
    quantity="pl",
    at_fn=pl_at,
    periods_fn=pl_periods,
    source="DFP + ITR BPP codigo 2.03 (or 2.08 for new-chart filers) — Patrimônio Líquido snapshot",
    category="bpp",
))
