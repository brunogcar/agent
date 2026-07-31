"""skills/cvm/financials/helpers.py -- Shared utilities for financials modes.

Holds cross-mode helpers used by both the fetchers (fetchers.py) and the
mode implementations (modes/*.py). Kept dependency-light so importing it
does NOT trigger calculations-engine imports (those require PLANNER_MODEL
env var via skills.cvm.calculations.*).

Public helpers:
  - _safe_call           : wraps a callable in try/except → None on any error.
  - _compute_ttm_section : builds the TTM section of a quarterly response.
  - fetch_statement_data : shared DFP+ITR fetcher used by the 5 standalone
                            statement modes (dva, dre, bpa, bpp, dfc). Added
                            in financials v1.12 — eliminates the duplicated
                            ~150-line fetch boilerplate that each standalone
                            mode carried inline.
"""
from __future__ import annotations

from typing import Callable

from skills.cvm.financials.metrics import compute_ttm, compute_ttm_with_engines


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_call(fn: Callable, *args, **kwargs):
    """Call a calculations engine/metric and return None on any error.

    Calculations engines call connect_dfp/connect_itr/connect_fre/cotahist,
    each of which may raise FileNotFoundError when the underlying DB is not
    synced. Many engines also need optional accounts (e.g. tax 3.08, cash
    1.01.01) that may not be filed for every company. Without this wrapper,
    one missing DB or account would crash the entire summary() call.
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


# Maps a quarter number (1-4) to its calendar end-date suffix (MM-DD).
_QUARTER_END_SUFFIX = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def _compute_ttm_section(company: str, result_periods: list[dict]) -> dict:
    """Build the TTM section of the quarterly response.

    [v1.3 migration] Uses compute_ttm_with_engines() to delegate TTM flow
    metrics (revenue, ebit, da, earnings, FCO/FCI/FCF, EBITDA) to the
    calculations engines instead of summing 4 standalone quarters. Snapshot
    metrics continue to use 4-quarter averaging inside compute_ttm_with_engines.

    Falls back to the legacy compute_ttm() (sum-of-4-quarters) when:
      - `company` is empty (defensive — should never happen in practice)
      - `result_periods` has no quarter info we can derive an end-date from
      - compute_ttm_with_engines raises (shouldn't happen — engines are
        wrapped in _safe_engine_call internally, but defensive nonetheless)

    Args:
        company: Ticker, name, or CNPJ (passed through to calculations engines).
        result_periods: list of period dicts (sorted oldest-first) with at
            least `year` and `quarter` keys on each entry.

    Returns:
        TTM dict shaped like {status, period_range, metrics, ratios} or
        {status: "insufficient_data"} when fewer than 4 quarters are present.
    """
    if not company or not result_periods:
        return compute_ttm(result_periods)

    # Derive the latest quarter's end date (TTM window ends here).
    latest = result_periods[-1]  # oldest-first → last is newest
    year = latest.get("year")
    qnum = latest.get("quarter")
    if year is None or qnum not in _QUARTER_END_SUFFIX:
        return compute_ttm(result_periods)
    ttm_date = f"{year}-{_QUARTER_END_SUFFIX[qnum]}"

    try:
        return compute_ttm_with_engines(company, ttm_date, result_periods)
    except Exception:
        # Defensive: engines are wrapped in _safe_engine_call inside
        # compute_ttm_with_engines, but if anything slips through, fall back
        # to the legacy sum-of-4-quarters derivation.
        return compute_ttm(result_periods)


# ── Shared standalone-statement fetcher ──────────────────────────────────────
#
# [v1.12] Extracted from the 5 standalone statement modes (dva, dre, bpa,
# bpp, dfc). Each of those modes had a near-identical ~150-line block of
# fetch+build boilerplate; the only differences were (a) the codigo list,
# (b) the grupo LIKE filter, and (c) the statement name in error messages.
# This helper takes those three as parameters and returns the standard
# {status, company, period_type, periods} response shape.

def fetch_statement_data(
    company: str,
    grupo_filter: str,
    codes: list[tuple[str, str, str]],  # (codigo, label, section)
    periods: int = 5,
    consolidado: int = 1,
    quarterly: int = 0,
    statement_name: str = "statement",
) -> dict:
    """Fetch statement data from DFP (annual) + ITR (quarterly).

    Shared by all 5 standalone statement modes (dva, dre, bpa, bpp, dfc).
    Returns the standard {status, company, period_type, periods} shape.

    Args:
        company: B3 ticker, name fragment, or CNPJ. Required.
        grupo_filter: SQL LIKE pattern for the ``grupo`` column. Examples:
            ``"%Valor Adicionado%"`` (DVA), ``"%Demonstração do Resultado%"``
            (DRE), ``"%Patrimonial Ativo%"`` (BPA),
            ``"%Patrimonial Passivo%"`` (BPP), ``"%Fluxo de Caixa%"`` (DFC).
        codes: List of ``(codigo, label, section)`` tuples. ``codigo`` is the
            CVM account code (e.g. ``"3.01"``); ``label`` is the human label
            to surface; ``section`` is the organizational bucket (e.g.
            ``"revenue"``, ``"distribution"``, ``"operating"``). The
            ``codigo`` list is also used to build the SQL ``IN (...)`` clause.
        periods: Number of periods to return. Default: 5.
        consolidado: 1=consolidated (default), 0=individual.
        quarterly: 1=quarterly (ITR meses=3/6/9 + DFP meses=12),
                   0=annual only (DFP meses=12). Default: 0.
        statement_name: Human-readable statement name used in error messages
                        (e.g. ``"DVA"``, ``"DRE"``, ``"BPA"``, ``"BPP"``,
                        ``"DFC"``). Default: ``"statement"``.

    Returns:
        Dict shaped like::

            {
                "status": "ok" | "not_found" | "not_synced" | "error",
                "company": <resolved name> (only when status="ok"),
                "period_type": "annual" | "quarterly" (only when status="ok"),
                "periods": [
                    {
                        "data_fim_exerc": "YYYY-MM-DD",
                        "meses": int,
                        "accounts": {
                            codigo: {"label": str, "section": str, "valor_brl": float},
                            ...
                        }
                    },
                    ...  # sorted newest-first
                ],
                "error": <str>  # only when status != "ok"
            }
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    # Lazy imports — keeps this module dependency-light (no DB imports at
    # module-load time). The standalone modes do the same.
    from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
    from data_sources.cvm._bridge import resolve_company

    code_list = [c[0] for c in codes]
    code_ph = ",".join("?" * len(code_list))
    label_map = {c[0]: c[1] for c in codes}
    section_map = {c[0]: c[2] for c in codes}

    def _fetch_rows(conn, empresa_ids, target_dates, consol):
        emp_ph = ",".join("?" * len(empresa_ids))
        date_ph = ",".join("?" * len(target_dates))
        return conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, meses, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND consolidado=?
                AND grupo LIKE ?
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *code_list, consol, grupo_filter, *target_dates),
        ).fetchall()

    def _build_periods_data(rows):
        periods_data: dict[str, dict] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = {"meses": r["meses"], "accounts": {}}
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key]["accounts"][r["codigo"]] = {
                "label": label_map.get(r["codigo"], r["descricao"]),
                "section": section_map.get(r["codigo"], "unknown"),
                "valor_brl": valor_brl,
            }
        return periods_data

    # ── Annual mode (DFP only) ────────────────────────────────────────────
    if not quarterly:
        conn = connect_dfp(read_only=True)
        try:
            empresa_ids, company_name = resolve_company(conn, company)
            if not empresa_ids:
                return {"status": "not_found",
                        "error": f"Company '{company}' not found in DFP"}

            emp_ph = ",".join("?" * len(empresa_ids))

            year_rows = conn.execute(
                f"""SELECT DISTINCT data_fim_exerc FROM contas
                    WHERE id_empresa IN ({emp_ph})
                    AND codigo IN ({code_ph})
                    AND meses=12 AND consolidado=?
                    AND grupo LIKE ?
                    ORDER BY data_fim_exerc DESC LIMIT ?""",
                (*empresa_ids, *code_list, consolidado, grupo_filter, periods),
            ).fetchall()

            if not year_rows:
                return {"status": "not_found",
                        "error": f"No {statement_name} data found for '{company}'"}

            target_dates = [r["data_fim_exerc"] for r in year_rows]
            rows = _fetch_rows(conn, empresa_ids, target_dates, consolidado)
            periods_data = _build_periods_data(rows)

            return {
                "status": "ok",
                "company": company_name,
                "period_type": "annual",
                "periods": [
                    {"data_fim_exerc": date, "meses": periods_data[date]["meses"],
                     "accounts": periods_data[date]["accounts"]}
                    for date in sorted(periods_data.keys(), reverse=True)
                ],
            }
        except FileNotFoundError as e:
            return {"status": "not_synced", "error": str(e)}
        finally:
            conn.close()

    # ── Quarterly mode (ITR + DFP) ────────────────────────────────────────
    # ITR has meses=3/6/9 (cumulative), DFP has meses=12 (annual).
    # We fetch all periods sorted by date DESC, LIMIT periods.
    dfp_conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(dfp_conn, company)
        if not empresa_ids:
            return {"status": "not_found",
                    "error": f"Company '{company}' not found in DFP"}

        emp_ph = ",".join("?" * len(empresa_ids))

        # Get DFP annual statement dates
        dfp_dates = dfp_conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND grupo LIKE ?
                ORDER BY data_fim_exerc DESC""",
            (*empresa_ids, *code_list, consolidado, grupo_filter),
        ).fetchall()
        dfp_date_list = [r["data_fim_exerc"] for r in dfp_dates]
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        dfp_conn.close()

    # Get ITR quarterly statement dates
    itr_date_list = []
    try:
        itr_conn = connect_itr(read_only=True)
        try:
            itr_empresa_ids, _ = resolve_company(itr_conn, company)
            if itr_empresa_ids:
                itr_emp_ph = ",".join("?" * len(itr_empresa_ids))
                itr_dates = itr_conn.execute(
                    f"""SELECT DISTINCT data_fim_exerc FROM contas
                        WHERE id_empresa IN ({itr_emp_ph})
                        AND codigo IN ({code_ph})
                        AND meses IN (3, 6, 9) AND consolidado=?
                        AND grupo LIKE ?
                        ORDER BY data_fim_exerc DESC""",
                    (*itr_empresa_ids, *code_list, consolidado, grupo_filter),
                ).fetchall()
                itr_date_list = [r["data_fim_exerc"] for r in itr_dates]
        finally:
            itr_conn.close()
    except FileNotFoundError:
        pass  # ITR not synced — return annual only

    # Merge + deduplicate dates (ITR Q4 = DFP annual, same date)
    all_dates = sorted(set(dfp_date_list + itr_date_list), reverse=True)[:periods]

    if not all_dates:
        return {"status": "not_found",
                "error": f"No {statement_name} data found for '{company}'"}

    # Fetch rows from both DBs
    all_rows = []

    # DFP rows
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_rows = _fetch_rows(dfp_conn, empresa_ids, all_dates, consolidado)
        all_rows.extend(dfp_rows)
    finally:
        dfp_conn.close()

    # ITR rows (if any ITR dates exist in all_dates)
    itr_dates_in_range = [d for d in all_dates if d in itr_date_list and d not in dfp_date_list]
    if itr_dates_in_range:
        try:
            itr_conn = connect_itr(read_only=True)
            try:
                itr_empresa_ids, _ = resolve_company(itr_conn, company)
                if itr_empresa_ids:
                    itr_rows = _fetch_rows(itr_conn, itr_empresa_ids, itr_dates_in_range, consolidado)
                    all_rows.extend(itr_rows)
            finally:
                itr_conn.close()
        except FileNotFoundError:
            pass

    periods_data = _build_periods_data(all_rows)

    return {
        "status": "ok",
        "company": company_name,
        "period_type": "quarterly",
        "periods": [
            {"data_fim_exerc": date, "meses": periods_data[date]["meses"],
             "accounts": periods_data[date]["accounts"]}
            for date in sorted(periods_data.keys(), reverse=True)
            if date in periods_data
        ],
    }
