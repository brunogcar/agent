"""engines/bpa/ppe.py -- Imobilizado (Property, Plant & Equipment) snapshot engine.

Gets consolidated Imobilizado (PP&E) at any historical date from DFP + ITR.

PP&E is a SNAPSHOT (point-in-time balance), not a flow. So this engine is
simpler than earnings.py -- no TTM derivation. We just find the most
recent BPA snapshot with data_fim_exerc <= date.

DATA SOURCE
-----------
DFP BPA (Balanço Patrimonial Ativo), codigo 1.02.03 = "Imobilizado"
  - Property, Plant & Equipment (net of accumulated depreciation), within
    Ativo Não Circulante (codigo 1.02).
  - Annual snapshot at Dec 31 (meses=12)
ITR BPA, same codigo 1.02.03
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, PP&E is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
PP&E snapshots computable from: 2010 onwards.

NOTE: codigo 1.02.03 is Imobilizado Líquido (net of accumulated
depreciation + impairments). For gross PP&E, a separate engine querying
codigo 1.02.03.01 (Imobilizado em Operação - custo) would be needed --
this is the net book value, which is what most balance-sheet ratios use.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.bpa.ppe import ppe_at, ppe_periods
    v = ppe_at("PETR4", "2024-06-30")        # -> 400e9 (BRL)
    ps = ppe_periods("PETR4")                # -> [{date, ppe}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Imobilizado Consolidado (BPA line within Ativo Não Circulante)
IMOBILIZADO_CODE = "1.02.03"


@engine_cached
def _get_dfp_ppe(company: str) -> dict[str, dict]:
    """Get all annual PP&E snapshots from DFP (codigo 1.02.03, meses=12, BPA).

    Returns: {"2024-12-31": {"value": 400e9, "year": 2024}, ...}
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
                 AND c.codigo = '{IMOBILIZADO_CODE}'
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
def _get_itr_ppe(company: str) -> dict[str, dict]:
    """Get all quarterly PP&E snapshots from ITR (codigo 1.02.03, meses 3/6/9, BPA).

    Returns: {"2024-06-30": {"value": 395e9, "meses": 6, "year": 2024}, ...}
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
                 AND c.codigo = '{IMOBILIZADO_CODE}'
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
def ppe_at(company: str, date: str) -> float | None:
    """Get Imobilizado (PP&E) closest to date (most recent snapshot <= date).

    PP&E is a point-in-time balance, so we just find the most recent BPA
    snapshot at or before the requested date. No TTM derivation needed.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        PP&E (net book value) in BRL, or None if no snapshot available at
        or before date.
    """
    dfp = _get_dfp_ppe(company)
    itr = _get_itr_ppe(company)

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
def ppe_periods(company: str) -> list[dict]:
    """Get all PP&E snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "ppe": 395e9}, ...]
    Sorted oldest-first. Each entry is a point where PP&E changed (new BPA
    snapshot filed). Deduplicated by date.

    Useful for building step-function PP&E overlays on price charts.
    """
    dfp = _get_dfp_ppe(company)
    itr = _get_itr_ppe(company)

    # Merge and dedupe by date (ITR takes precedence if same date -- same value anyway)
    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "ppe": by_date[d]} for d in sorted(by_date.keys())]


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402
register_engine(EngineSpec(
    name="ppe",
    quantity="ppe",
    at_fn=ppe_at,
    periods_fn=ppe_periods,
    source="DFP + ITR BPA codigo 1.02.03 (Imobilizado snapshot)",
    category="bpa",
))
