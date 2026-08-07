"""engines/bpp/pl.py — Patrimônio Líquido (equity) snapshot engine.

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

FALLBACK + ZERO-VALUE TRAP  [v1.6 review-fix]
----------------------------------------------
Some DFP/ITR rows carry ``valor = 0`` or NULL for codigo 2.03 — a data-
quality issue (e.g. a company filed a BPP with a placeholder zero in the
total-equity line, or the escala metadata is corrupt).  The naive
``float(r["valor"] or 0) * escala`` path returns ``0.0`` for these rows,
which silently breaks every downstream ratio (ROE → division by zero,
VPA → zero, debt_equity → infinity).

``_pick_pl_value()`` fixes this by:

  1. Querying BOTH 2.03 (Patrimônio Líquido — the total) AND 2.08
     (Lucros ou Prejuízos Acumulados — retained earnings, a sub-component)
     in a single pass.
  2. For each snapshot date, preferring 2.03 **if its value is non-zero**.
  3. Falling back to 2.08 **only if** (a) 2.03 is missing or zero for that
     date, AND (b) the 2.08 row's ``descricao`` contains "Lucro" or
     "Prejuízo" (description check — prevents matching an unrelated
     2.08.xx sub-code), AND (c) the 2.08 value is itself non-zero.
  4. If neither qualifies, the date is dropped entirely (no zero-PL
     snapshot pollutes the series).

NOTE: 2.08 is retained earnings only — NOT total equity.  Using it as PL
is a last-resort approximation for old-chart filers (pre-2010 reorg) that
omit 2.03.  The ``source_code`` field in the returned dict lets callers
detect when the fallback fired.

DATA RANGE
----------
DFP: 2010-present (annual)
ITR: 2011-present (quarterly)
PL snapshots computable from: 2010 onwards.

Standalone module: importable by historical skill + future backtest skill.

Usage:
    from skills.cvm.calculations.engines.bpp.pl import pl_at, pl_periods
    v = pl_at("PETR4", "2024-06-30")        # → 380e9 (BRL)
    ps = pl_periods("PETR4")                # → [{date, pl}, ...]
"""

from __future__ import annotations

from core.br_validator import parse_escala
from data_sources.cvm._db import connect_dfp, connect_itr
from data_sources.cvm._bridge import resolve_company
from skills._base import engine_cached  # [v1.8 F7]


# CVM account code for Patrimônio Líquido Consolidado (BPP group) — the
# total equity figure we want.
PATRIMONIO_LIQUIDO_CODE = "2.03"

# Fallback code: Lucros ou Prejuízos Acumulados (retained earnings).  Only
# used when 2.03 is missing/zero for a snapshot date AND the row's
# descricao confirms it is the retained-earnings account (not some other
# 2.08.xx sub-code).  See _pick_pl_value() docstring.
RETAINED_EARNINGS_CODE = "2.08"

# Descricao substrings that identify the retained-earnings account.  The
# description check prevents false matches on unrelated 2.08.xx codes.
_RETAINED_EARNINGS_DESC_TOKENS = ("lucro", "prejuízo", "prejuizo")


def _pick_pl_value(candidates: list[dict]) -> tuple[float | None, str | None]:
    """Pick the best PL value from candidate rows for a single snapshot date.

    Each candidate is ``{"codigo": str, "valor": float, "escala": float,
    "descricao": str}`` (escala already parsed by the caller is fine, OR
    raw — see note below).  Returns ``(value_in_brl, source_code)``.

    Selection order (the "zero-value trap" fix):

      1. The 2.03 candidate with ``valor != 0`` (and not None).  Escala
         is applied.
      2. The 2.08 candidate with ``descricao`` containing "Lucro" or
         "Prejuízo" (case-insensitive) AND ``valor != 0``.  Escala applied.
      3. ``(None, None)`` if neither qualifies — the date is dropped.

    Args:
        candidates: list of row dicts for the SAME data_fim_exerc.  May
            contain 0, 1, or 2 entries (2.03 only, 2.08 only, or both).

    Returns:
        ``(value_brl_or_none, source_code_or_none)`` where source_code is
        "2.03" or "2.08" (or None if nothing qualified).
    """
    val_203: float | None = None
    val_208: float | None = None

    for c in candidates:
        codigo = c.get("codigo")
        # valor may be None (DB NULL) or 0 (data error) — both are "zero"
        # for the purpose of the trap.  ``float(None or 0)`` = 0.0, which
        # we explicitly reject below via the ``!= 0`` check.
        escala = parse_escala(c.get("escala"))
        raw = c.get("valor")
        valor = float(raw) * escala if raw is not None else 0.0

        if codigo == PATRIMONIO_LIQUIDO_CODE:
            # [zero-value trap fix] Only accept non-zero 2.03.
            if valor != 0:
                val_203 = valor
        elif codigo == RETAINED_EARNINGS_CODE:
            # Description check: must look like retained earnings.
            desc = (c.get("descricao") or "").lower()
            if any(tok in desc for tok in _RETAINED_EARNINGS_DESC_TOKENS):
                if valor != 0:
                    val_208 = valor

    if val_203 is not None:
        return val_203, PATRIMONIO_LIQUIDO_CODE
    if val_208 is not None:
        return val_208, RETAINED_EARNINGS_CODE
    return None, None


def _group_rows_by_date(rows) -> dict[str, list[dict]]:
    """Group query rows (sqlite3.Row) by data_fim_exerc into plain dicts.

    Each group is a list of ``{codigo, valor, escala, descricao}`` dicts
    ready for ``_pick_pl_value()``.
    """
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        d = r["data_fim_exerc"]
        by_date.setdefault(d, []).append({
            "codigo": r["codigo"],
            "valor": r["valor"],
            "escala": r["escala"],
            "descricao": r["descricao"],
        })
    return by_date


def _get_dfp_pl(company: str) -> dict[str, dict]:
    """Get all annual PL snapshots from DFP (codigo 2.03 [+ 2.08 fallback], meses=12, BPP).

    Returns: {"2024-12-31": {"value": 380e9, "year": 2024, "source_code": "2.03"}, ...}
    Values are in BRL (escala applied).  Dates with only zero-value rows are
    dropped (zero-value trap fix — see module docstring).
    """
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.codigo, c.valor, c.escala, c.descricao,
                      c.data_fim_exerc, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ('{PATRIMONIO_LIQUIDO_CODE}',
                                  '{RETAINED_EARNINGS_CODE}')
                 AND c.meses = 12
               ORDER BY e.ano DESC""",
            empresa_ids,
        ).fetchall()

        # Map ano (year) from the FIRST row seen per date (both 2.03 and
        # 2.08 share the same ano for a given data_fim_exerc).
        date_to_year: dict[str, int] = {}
        for r in rows:
            d = r["data_fim_exerc"]
            if d not in date_to_year:
                date_to_year[d] = r["ano"]

        grouped = _group_rows_by_date(rows)
        result = {}
        for d, candidates in grouped.items():
            value, source = _pick_pl_value(candidates)
            if value is not None:
                result[d] = {
                    "value": value,
                    "year": date_to_year[d],
                    "source_code": source,
                }
        return result
    finally:
        conn.close()


def _get_itr_pl(company: str) -> dict[str, dict]:
    """Get all quarterly PL snapshots from ITR (codigo 2.03 [+ 2.08 fallback], meses 3/6/9, BPP).

    Returns: {"2024-06-30": {"value": 375e9, "meses": 6, "year": 2024, "source_code": "2.03"}, ...}
    Values are in BRL (escala applied).  Dates with only zero-value rows are
    dropped (zero-value trap fix — see module docstring).
    """
    conn = connect_itr(read_only=True)
    try:
        empresa_ids, _ = resolve_company(conn, company)
        if not empresa_ids:
            return {}
        emp_ph = ",".join("?" * len(empresa_ids))
        rows = conn.execute(
            f"""SELECT c.codigo, c.valor, c.escala, c.descricao,
                      c.data_fim_exerc, c.meses, e.ano
               FROM contas c JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_ph})
                 AND c.consolidado = 1
                 AND c.codigo IN ('{PATRIMONIO_LIQUIDO_CODE}',
                                  '{RETAINED_EARNINGS_CODE}')
                 AND c.meses IN (3, 6, 9)
               ORDER BY e.ano DESC, c.data_fim_exerc DESC""",
            empresa_ids,
        ).fetchall()

        date_to_meta: dict[str, dict] = {}
        for r in rows:
            d = r["data_fim_exerc"]
            if d not in date_to_meta:
                date_to_meta[d] = {"meses": r["meses"], "year": r["ano"]}

        grouped = _group_rows_by_date(rows)
        result = {}
        for d, candidates in grouped.items():
            value, source = _pick_pl_value(candidates)
            if value is not None:
                meta = date_to_meta[d]
                result[d] = {
                    "value": value,
                    "meses": meta["meses"],
                    "year": meta["year"],
                    "source_code": source,
                }
        return result
    finally:
        conn.close()


@engine_cached
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


@engine_cached
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
    source="DFP + ITR BPP codigo 2.03 (Patrimônio Líquido snapshot)",
    category="bpp",
))
