"""engines/debt.py -- Total debt (Empréstimos e Financiamentos) snapshot engine.

Gets consolidated total debt at any historical date from DFP + ITR.
Debt is the sum of two BPP accounts:
  - 2.01.04 = Empréstimos e Financiamentos (current / short-term debt)
  - 2.02.01 = Empréstimos e Financiamentos (non-current / long-term debt)

Debt is a SNAPSHOT (point-in-time balance), like PL and assets. No TTM
derivation -- we just find the most recent BPP snapshot <= date and sum
both codes.

DATA SOURCE
-----------
DFP BPP (Balanço Patrimonial Passivo), codigos 2.01.04 + 2.02.01
  - Annual snapshot at Dec 31 (meses=12)
ITR BPP, same codigos
  - Quarterly snapshot at Mar/Jun/Sep 30 (meses=3/6/9)

Together: ~4 snapshots per year. Between snapshots, debt is constant.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
Debt snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.debt import debt_at, debt_periods
    d = debt_at("PETR4", "2024-06-30")        # -> 250e9 (BRL)
    ps = debt_periods("PETR4")                # -> [{date, debt}, ...]
"""
from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company


# CVM account codes for Empréstimos e Financiamentos (loans + financing)
DEBT_CODES = ("2.01.04", "2.02.01")


def _query_debt_snapshots(conn, empresa_ids: list[int]) -> dict[str, float]:
    """Query debt snapshots (sum of 2.01.04 + 2.02.01) grouped by data_fim_exerc.

    Returns: {"2024-06-30": 250e9, ...} -- total debt per snapshot date.
    """
    emp_ph = ",".join("?" * len(empresa_ids))
    code_ph = ",".join("?" * len(DEBT_CODES))
    rows = conn.execute(
        f"""SELECT c.data_fim_exerc, c.meses,
                  SUM(float(c.valor or 0) * CASE c.escala
                      WHEN 'MIL' THEN 1000
                      WHEN 'MILHÃO' THEN 1000000
                      WHEN 'MILHOES' THEN 1000000
                      WHEN 'Milhão' THEN 1000000
                      WHEN 'UNIDADE' THEN 1
                      WHEN 'Unidade' THEN 1
                      ELSE 1 END) as total_debt
           FROM contas c
           WHERE c.id_empresa IN ({emp_ph})
             AND c.consolidado = 1
             AND c.codigo IN ({code_ph})
           GROUP BY c.data_fim_exerc, c.meses
           ORDER BY c.data_fim_exerc DESC""",
        empresa_ids + list(DEBT_CODES),
    ).fetchall()

    # parse_escala can't be used in SQL (it's a Python function), so we
    # handle it in the query with a CASE. But parse_escala handles more
    # edge cases. Let's do it in Python instead for correctness.
    # Actually, let's re-query and do it in Python for robustness.
    return {}


def _get_dfp_debt(company: str) -> dict[str, dict]:
    """Get all annual debt snapshots from DFP (codigos 2.01.04 + 2.02.01, meses=12).

    Returns: {"2024-12-31": {"value": 250e9, "year": 2024}, ...}
    Values are in BRL (escala applied). Sum of both codes.
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(DEBT_CODES))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, e.ano, c.codigo
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ({code_ph})
                 AND c.meses = 12
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids + list(DEBT_CODES),
        ).fetchall()

        # Sum both codes per date
        by_date: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            date = r["data_fim_exerc"]
            if date not in by_date:
                by_date[date] = {"value": 0.0, "year": r["ano"]}
            by_date[date]["value"] += valor
        return by_date
    finally:
        conn.close()


def _get_itr_debt(company: str) -> dict[str, dict]:
    """Get all quarterly debt snapshots from ITR (codigos 2.01.04 + 2.02.01, meses 3/6/9).

    Returns: {"2024-06-30": {"value": 240e9, "meses": 6, "year": 2024}, ...}
    Values are in BRL (escala applied). Sum of both codes.
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(DEBT_CODES))
        rows = conn.execute(
            f"""SELECT c.valor, c.escala, c.data_fim_exerc, c.meses, e.ano, c.codigo
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ({code_ph})
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids + list(DEBT_CODES),
        ).fetchall()

        by_date: dict[str, dict] = {}
        for r in rows:
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            date = r["data_fim_exerc"]
            if date not in by_date:
                by_date[date] = {"value": 0.0, "meses": r["meses"], "year": r["ano"]}
            by_date[date]["value"] += valor
        return by_date
    finally:
        conn.close()


def debt_at(company: str, date: str) -> float | None:
    """Get total debt closest to date (most recent snapshot <= date).

    Debt is a point-in-time balance (snapshot), so we just find the most
    recent BPP snapshot at or before the requested date. No TTM derivation.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD.

    Returns:
        Total debt in BRL (sum of 2.01.04 + 2.02.01), or None if no snapshot.
    """
    dfp = _get_dfp_debt(company)
    itr = _get_itr_debt(company)

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


def debt_periods(company: str) -> list[dict]:
    """Get all debt snapshot periods for a company.

    Returns: [{"date": "2024-06-30", "debt": 240e9}, ...]
    Sorted oldest-first. Deduplicated by date.
    """
    dfp = _get_dfp_debt(company)
    itr = _get_itr_debt(company)

    by_date: dict[str, float] = {}
    for d, v in dfp.items():
        by_date[d] = v["value"]
    for d, v in itr.items():
        by_date[d] = v["value"]

    return [{"date": d, "debt": by_date[d]} for d in sorted(by_date.keys())]


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import EngineSpec, register_engine  # noqa: E402

register_engine(EngineSpec(
    name="debt",
    quantity="debt",
    at_fn=debt_at,
    periods_fn=debt_periods,
    source="DFP + ITR BPP codigos 2.01.04+2.02.01 (Empréstimos e Financiamentos snapshot)",
    category="bpp",
))
