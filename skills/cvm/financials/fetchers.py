"""skills/cvm/financials/fetchers.py -- Internal data fetching from DFP/ITR.

Holds the internal helpers that query the DFP/ITR SQLite databases and
build the statement dicts consumed by the mode functions in modes/*.py.

Functions:
  Summary builders (annual + quarterly):
    - _build_summary             : dispatches to annual or quarterly builder
    - _build_annual_summary      : DFP (meses=12) + DVA proventos
    - _build_quarterly_summary   : ITR cumulative + DFP annual → standalone quarters

  Cumulative-data fetcher:
    - _fetch_quarterly_cumulative: ITR (meses=3/6/9) or DFP (meses=12) bulk fetch
    - _fetch_cumulative_full     : same but for arbitrary codes + preserves metadata
    - _build_quarter_labels      : last-N-quarters label list

  Per-quarter value getters (used by both summary + complete modes):
    - _get_snapshot_value        : BPA/BPP period-end value (Q1-Q3 ITR, Q4 DFP)
    - _get_cumulative_value      : flow cumulative value (Q1-Q3 ITR, Q4 DFP)
    - _get_prev_cumulative       : previous-quarter cumulative (for standalone derivation)

  Metric extraction:
    - _extract_metrics           : {codigo: valor} → named-metrics dict

  Complete-mode fetchers:
    - _fetch_complete_annual     : full key-code statements from DFP
    - _fetch_complete_quarterly  : full key-code statements from ITR + DFP

  [v1.24] Multi-statement fetchers (5 statements in ONE SQL query):
    - _fetch_all_statements_annual    : DFP-only annual (BPA/BPP/DRE/DFC/DVA)
    - _fetch_all_statements_quarterly : ITR+DFP quarterly standalone (BPA/BPP snapshot,
                                        DRE/DFC/DVA flow = curr_cum − prev_cum)
"""
from __future__ import annotations

from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
from data_sources.cvm._bridge import resolve_company
from skills.cvm.financials.metrics import (
    SUMMARY_CODES,
    compute_ebitda,
    compute_ratios,
    _f,
)
from skills.cvm.financials.helpers import _compute_ttm_section


# ── Internal: build summary (annual or quarterly) ────────────────────────────

def _build_summary(company: str, periods: int, consolidado: int, is_quarterly: bool) -> dict:
    """Build summary metrics + ratios for annual or quarterly."""
    if is_quarterly:
        return _build_quarterly_summary(company, periods, consolidado)
    else:
        return _build_annual_summary(company, periods, consolidado)


def _build_annual_summary(company: str, periods: int, consolidado: int) -> dict:
    """Annual summary from DFP (meses=12) + DVA."""
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        codes = list(SUMMARY_CODES.keys())
        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(codes))

        # Get last N years
        year_rows = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                ORDER BY data_fim_exerc DESC LIMIT ?""",
            (*empresa_ids, *codes, consolidado, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found", "error": f"No annual data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        date_ph = ",".join("?" * len(target_dates))

        rows = conn.execute(
            f"""SELECT codigo, descricao, grupo, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, consolidado, *target_dates),
        ).fetchall()

        # Group by year
        by_year: dict[str, dict] = {}
        for r in rows:
            year_key = r["data_fim_exerc"][:4]  # "2023-12-31" → "2023"
            if year_key not in by_year:
                by_year[year_key] = {}
            escala = parse_escala(r["escala"])
            valor = float(r["valor"] or 0) * escala
            by_year[year_key][r["codigo"]] = valor

        # Build metrics + ratios per year
        result_periods = []
        for year_key in sorted(by_year.keys(), reverse=True):
            vals = by_year[year_key]
            metrics = _extract_metrics(vals)
            # [v1.0.1] compute_ebitda returns (value, method) tuple
            metrics["ebitda"], metrics["ebitda_method"] = compute_ebitda(
                metrics.get("ebit"), metrics.get("da"))
            ratios = compute_ratios(metrics, is_quarterly=False)
            result_periods.append({
                "period": year_key,
                "data_fim_exerc": f"{year_key}-12-31",
                "metrics": metrics,
                "ratios": ratios,
            })

        return {"status": "ok", "company": company_name,
                "period_type": "annual", "periods": result_periods}
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()


def _build_quarterly_summary(company: str, periods: int, consolidado: int) -> dict:
    """Quarterly summary with standalone quarters derived from ITR + DFP."""
    # [v1.0.1 P0 fix] Resolve empresa_ids SEPARATELY for DFP and ITR.
    # DFP and ITR are separate SQLite files with independent autoincrement IDs.
    # Using DFP's IDs to query ITR returns wrong/empty rows in production.
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_empresa_ids, company_name = resolve_company(dfp_conn, company)
        if not dfp_empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        dfp_conn.close()

    # Resolve ITR empresa_ids separately (may differ from DFP's)
    try:
        itr_conn = connect_itr(read_only=True)
        itr_empresa_ids, _ = resolve_company(itr_conn, company)
        itr_conn.close()
    except FileNotFoundError:
        itr_empresa_ids = []  # ITR not synced — Q4 derivation will be incomplete
    except Exception:
        itr_empresa_ids = []

    # Determine which years to fetch (need current + prior year for Q4 derivation)
    years_needed = (periods // 4) + 2  # current + prior + buffer

    # Fetch ITR data (using ITR's own empresa_ids)
    itr_data = _fetch_quarterly_cumulative(itr_empresa_ids, consolidado, years_needed, "ITR")
    # Fetch DFP annual data (using DFP's own empresa_ids)
    dfp_data = _fetch_quarterly_cumulative(dfp_empresa_ids, consolidado, years_needed, "DFP")

    if not itr_data and not dfp_data:
        return {"status": "not_found", "error": f"No quarterly data found for '{company}'"}

    # Build quarter labels with cumulative values per code
    # quarter_label = "1T2026", "4T2025", etc.
    # For each code, collect {quarter_label: cumulative_value}
    result_periods = []
    all_quarters = _build_quarter_labels(itr_data, dfp_data, periods)

    for q_label, year, q_num in all_quarters:
        # Gather cumulative values for this quarter
        cum_values = {}
        for code in SUMMARY_CODES:
            grupo, _ = SUMMARY_CODES[code]
            is_snapshot = grupo in ("BPA", "BPP")

            if is_snapshot:
                # Snapshots: use period-end value
                val = _get_snapshot_value(code, q_label, year, q_num, itr_data, dfp_data)
            else:
                # Flows: use cumulative value
                val = _get_cumulative_value(code, q_label, year, q_num, itr_data, dfp_data)
            cum_values[code] = val

        # For flows, derive standalone
        standalone_values = {}
        for code, (grupo, _) in SUMMARY_CODES.items():
            is_snapshot = grupo in ("BPA", "BPP")
            if is_snapshot:
                standalone_values[code] = cum_values.get(code)
            else:
                # [v1.0.1 P1 fix] Standalone derivation:
                # Q1: standalone = cumulative (no prior needed — fiscal year resets Jan 1)
                # Q2/Q3/Q4: standalone = cumulative - prev_cumulative
                # If prev_cum is missing for Q2-Q4, standalone = None (can't derive)
                prev_cum = _get_prev_cumulative(code, year, q_num, itr_data, dfp_data)
                curr_cum = cum_values.get(code)
                if curr_cum is None:
                    standalone_values[code] = None
                elif q_num == 1:
                    # Q1 standalone = Q1 cumulative
                    standalone_values[code] = curr_cum
                elif prev_cum is not None:
                    standalone_values[code] = curr_cum - prev_cum
                else:
                    # Q2-Q4 but prev_cum missing — can't derive standalone
                    standalone_values[code] = None

        metrics = _extract_metrics(standalone_values)
        # [v1.0.1] compute_ebitda returns (value, method) tuple
        metrics["ebitda"], metrics["ebitda_method"] = compute_ebitda(
            metrics.get("ebit"), metrics.get("da"))
        ratios = compute_ratios(metrics, is_quarterly=True)

        result_periods.append({
            "period": q_label,
            "year": year,
            "quarter": q_num,
            "metrics": metrics,
            "ratios": ratios,
        })

    return {"status": "ok", "company": company_name,
            "period_type": "quarterly", "periods": result_periods,
            "ttm": _compute_ttm_section(company, result_periods)}


# ── Internal: data fetching helpers ──────────────────────────────────────────

def _fetch_quarterly_cumulative(
    empresa_ids: list[int],
    consolidado: int,
    years_needed: int,
    source: str,
) -> dict:
    """Fetch cumulative quarterly data from ITR or annual from DFP.

    Returns: {year: {meses: {codigo: valor}}} for the given source.

    [v1.16 3T2025-bugfix] The old LIMIT ``years_needed * len(codes) * 4``
    did NOT account for multiple empresa_ids (consolidated subsidiaries).
    When a company had 2+ empresa_ids, each (year, meses, codigo) row was
    duplicated per empresa_id, and the LIMIT cut off before reaching the
    oldest requested quarter. This caused 3T2025 to silently disappear
    from TTM output even though the data was present in the ITR DB
    (669k rows for 2025-09-30).

    Fix: scale the LIMIT by ``max(len(empresa_ids), 1)`` and bump the
    per-year multiplier from 4 to 5 (buffer for non-calendar filers
    whose data_fim_exerc falls outside standard quarter-end dates).
    The ``ORDER BY data_fim_exerc DESC`` + LIMIT still returns only the
    most recent N rows, which is exactly what we want — we don't need a
    separate year filter (and a year filter would break test fixtures
    that use fixed older years like 2023).
    """
    codes = list(SUMMARY_CODES.keys())
    emp_ph = ",".join("?" * len(empresa_ids))
    code_ph = ",".join("?" * len(codes))

    if source == "ITR":
        conn = connect_itr(read_only=True)
        meses_filter = "AND meses IN (3, 6, 9)"
    else:  # DFP
        conn = connect_dfp(read_only=True)
        meses_filter = "AND meses = 12"

    # Safety-net LIMIT: per (year, meses, empresa_id, codigo) row.
    # `* 5` instead of `* 4` gives a buffer for non-calendar filers.
    # `* n_emp` ensures we don't cut off older quarters when the company
    # has multiple consolidated empresa_ids.
    n_emp = max(len(empresa_ids), 1)
    safety_limit = years_needed * len(codes) * n_emp * 5

    try:
        rows = conn.execute(
            f"""SELECT codigo, descricao, grupo, data_fim_exerc, meses, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND consolidado = ?
                {meses_filter}
                ORDER BY data_fim_exerc DESC
                LIMIT ?""",
            (*empresa_ids, *codes, consolidado, safety_limit),
        ).fetchall()
    except FileNotFoundError:
        return {}
    finally:
        conn.close()

    # Organize: {year: {meses: {codigo: valor}}}
    # When multiple empresa_ids return rows for the same (year, meses,
    # codigo), the last one seen wins (DESC order means the most recent
    # empresa_id — typically the consolidated parent — wins).
    result: dict = {}
    for r in rows:
        year = int(r["data_fim_exerc"][:4])
        meses = r["meses"]
        if year not in result:
            result[year] = {}
        if meses not in result[year]:
            result[year][meses] = {}
        escala = parse_escala(r["escala"])
        result[year][meses][r["codigo"]] = float(r["valor"] or 0) * escala

    return result


def _fetch_cumulative_full(
    empresa_ids: list[int],
    consolidado: int,
    years_needed: int,
    source: str,
    codes: list[str],
) -> dict:
    """[v1.24] Like _fetch_quarterly_cumulative() but for arbitrary codes AND
    preserves ``descricao`` + ``grupo`` metadata.

    Returns:
        ``{year: {meses: {codigo: {"valor", "descricao", "grupo"}}}}``

    The leaf is a dict (not a bare float) so callers building complete-mode
    statement tables can reuse the official CVM ``descricao`` label without
    re-querying the DB. ``_build_quarter_labels`` still works because it
    only checks ``data[year][meses]`` for truthiness — a non-empty dict is
    truthy.

    Used by ``_fetch_all_statements_quarterly()`` which needs ALL
    ``KEY_CODES_BY_GRUPO`` codes (not just ``SUMMARY_CODES``) so the
    quarterly statement tabs can render the same code-level detail as the
    annual tabs.
    """
    if not empresa_ids or not codes:
        return {}

    emp_ph = ",".join("?" * len(empresa_ids))
    code_ph = ",".join("?" * len(codes))

    if source == "ITR":
        conn = connect_itr(read_only=True)
        meses_filter = "AND meses IN (3, 6, 9)"
    else:  # DFP
        conn = connect_dfp(read_only=True)
        meses_filter = "AND meses = 12"

    n_emp = max(len(empresa_ids), 1)
    safety_limit = years_needed * len(codes) * n_emp * 5

    try:
        rows = conn.execute(
            f"""SELECT codigo, descricao, grupo, data_fim_exerc, meses, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND consolidado = ?
                {meses_filter}
                ORDER BY data_fim_exerc DESC
                LIMIT ?""",
            (*empresa_ids, *codes, consolidado, safety_limit),
        ).fetchall()
    except FileNotFoundError:
        return {}
    finally:
        conn.close()

    result: dict = {}
    for r in rows:
        year = int(r["data_fim_exerc"][:4])
        meses = r["meses"]
        if year not in result:
            result[year] = {}
        if meses not in result[year]:
            result[year][meses] = {}
        escala = parse_escala(r["escala"])
        # Last write wins (DESC order means the most recent empresa_id wins
        # when multiple consolidated subsidiaries return the same code).
        result[year][meses][r["codigo"]] = {
            "valor": float(r["valor"] or 0) * escala,
            "descricao": r["descricao"],
            "grupo": r["grupo"],
        }

    return result


def _build_quarter_labels(itr_data: dict, dfp_data: dict, periods: int) -> list:
    """Build list of (quarter_label, year, quarter_num) for the last N quarters.

    Quarters are in DESC order (newest first). Q4 comes from DFP (meses=12),
    Q1-Q3 from ITR (meses=3,6,9).
    """
    # Collect all available (year, quarter) pairs
    available = []
    all_years = set(itr_data.keys()) | set(dfp_data.keys())
    for year in all_years:
        if dfp_data.get(year, {}).get(12):  # Q4 available
            available.append((year, 4))
        if itr_data.get(year, {}).get(9):  # Q3 available
            available.append((year, 3))
        if itr_data.get(year, {}).get(6):  # Q2 available
            available.append((year, 2))
        if itr_data.get(year, {}).get(3):  # Q1 available
            available.append((year, 1))

    # Sort newest-first, take first N
    available.sort(key=lambda x: (x[0], x[1]), reverse=True)
    available = available[:periods]

    # Sort oldest-first for derivation, then we'll reverse at the end
    available.sort(key=lambda x: (x[0], x[1]))

    return [(f"{q}T{y}", y, q) for y, q in available]


def _get_snapshot_value(code, q_label, year, q_num, itr_data, dfp_data):
    """Get snapshot value (BPA/BPP) for a quarter. Q1-Q3 from ITR, Q4 from DFP."""
    if q_num == 4:
        return dfp_data.get(year, {}).get(12, {}).get(code)
    else:
        meses = {1: 3, 2: 6, 3: 9}[q_num]
        return itr_data.get(year, {}).get(meses, {}).get(code)


def _get_cumulative_value(code, q_label, year, q_num, itr_data, dfp_data):
    """Get cumulative flow value for a quarter. Q1-Q3 from ITR, Q4 from DFP."""
    return _get_snapshot_value(code, q_label, year, q_num, itr_data, dfp_data)


def _get_prev_cumulative(code, year, q_num, itr_data, dfp_data):
    """Get the cumulative value for the PREVIOUS quarter (for standalone derivation).

    [v1.0.1 P1 fix] Q1 does NOT need a previous quarter — Q1 cumulative IS the
    standalone value (fiscal year resets Jan 1). Returns None for Q1 so the
    caller uses Q1 cumulative directly.

    Q2: previous = Q1 (meses=3) of same year from ITR
    Q3: previous = Q2 (meses=6) of same year from ITR
    Q4: previous = Q3 (meses=9) of same year from ITR
    """
    if q_num == 1:
        # Q1 standalone = Q1 cumulative (no subtraction needed)
        return None
    elif q_num == 2:
        return itr_data.get(year, {}).get(3, {}).get(code)
    elif q_num == 3:
        return itr_data.get(year, {}).get(6, {}).get(code)
    elif q_num == 4:
        return itr_data.get(year, {}).get(9, {}).get(code)
    return None


def _extract_metrics(vals: dict) -> dict:
    """Extract named metrics from a {codigo: valor} dict.

    [v1.2] D&A fallback: try DFC_MI (6.01.01.02) first, then DFC_MD code
    (6.02.01.02) for direct-method filers. compute_ebitda() gets whichever
    is non-None.

    [v1.5 fix-tests-version] Removed 6.01.04 from the D&A fallback chain.
    The 6.01.04 code is "Variações Cambiais" (foreign exchange variations)
    under DFC operating cash flow — it is NOT depreciation & amortization.
    Using it as a D&A fallback incorrectly inflated EBITDA for filers that
    reported FX variations but no D&A in their indirect-method DFC. The
    6.01.04 value is now exposed as the dedicated `variacao_cambial` key.
    """
    divida_bruta = None
    d_circ = _f(vals, "2.01.04")
    d_ncirc = _f(vals, "2.02.01")
    if d_circ is not None or d_ncirc is not None:
        divida_bruta = (d_circ or 0) + (d_ncirc or 0)

    # [v1.2] D&A: try indirect method first, then direct method fallback
    # [v1.5] Removed 6.01.04 from this chain — it is FX variation, not D&A.
    da = _f(vals, "6.01.01.02")
    if da is None:
        da = _f(vals, "6.02.01.02")  # DFC_MD direct method

    return {
        "ativo_total":          _f(vals, "1"),
        "caixa":                _f(vals, "1.01.01"),
        "patrimonio_liquido":   _f(vals, "2.03"),
        "divida_bruta":         divida_bruta,
        "receita_liquida":      _f(vals, "3.01"),
        "lucro_bruto":          _f(vals, "3.03"),
        "ebit":                 _f(vals, "3.05"),
        "resultado_financeiro": _f(vals, "3.06"),
        "lucro_liquido":        _f(vals, "3.11"),
        "fco":                  _f(vals, "6.01"),
        "fci":                  _f(vals, "6.02"),
        "fcf":                  _f(vals, "6.03"),
        "da":                   da,
        "variacao_cambial":     _f(vals, "6.01.04"),
        "proventos":            _f(vals, "7.08.04"),
    }


# ── Internal: complete mode fetchers ─────────────────────────────────────────

def _fetch_complete_annual(company, codes, grupo_filter, consolidado, periods) -> dict:
    """Fetch full annual statements (key codes only) from DFP."""
    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(codes))

        year_rows = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                ORDER BY data_fim_exerc DESC LIMIT ?""",
            (*empresa_ids, *codes, consolidado, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found", "error": f"No data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        date_ph = ",".join("?" * len(target_dates))

        rows = conn.execute(
            f"""SELECT codigo, descricao, grupo, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, consolidado, *target_dates),
        ).fetchall()

        by_year: dict[str, list] = {}
        for r in rows:
            year_key = r["data_fim_exerc"][:4]
            if year_key not in by_year:
                by_year[year_key] = []
            escala = parse_escala(r["escala"])
            by_year[year_key].append({
                "codigo": r["codigo"],
                "descricao": r["descricao"],
                "grupo": r["grupo"],
                "valor_brl": float(r["valor"] or 0) * escala,
            })

        return {
            "status": "ok",
            "company": company_name,
            "period_type": "annual",
            "grupo_filter": grupo_filter or "all",
            "periods": [
                {"year": y, "data_fim_exerc": f"{y}-12-31", "accounts": by_year[y]}
                for y in sorted(by_year.keys(), reverse=True)
            ],
        }
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()


def _fetch_complete_quarterly(company, codes, grupo_filter, consolidado, periods) -> dict:
    """Fetch full quarterly statements (key codes, cumulative) from ITR + DFP."""
    # [v1.0.1 P0 fix] Resolve empresa_ids SEPARATELY for DFP and ITR.
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_empresa_ids, company_name = resolve_company(dfp_conn, company)
        if not dfp_empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        dfp_conn.close()

    # Resolve ITR empresa_ids separately
    try:
        itr_conn = connect_itr(read_only=True)
        itr_empresa_ids, _ = resolve_company(itr_conn, company)
        itr_conn.close()
    except (FileNotFoundError, Exception):
        itr_empresa_ids = []

    years_needed = (periods // 4) + 2
    itr_data = _fetch_quarterly_cumulative(itr_empresa_ids, consolidado, years_needed, "ITR")
    dfp_data = _fetch_quarterly_cumulative(dfp_empresa_ids, consolidado, years_needed, "DFP")

    if not itr_data and not dfp_data:
        return {"status": "not_found", "error": f"No quarterly data found for '{company}'"}

    all_quarters = _build_quarter_labels(itr_data, dfp_data, periods)
    result_periods = []
    for q_label, year, q_num in all_quarters:
        accounts = []
        for code in codes:
            val = _get_snapshot_value(code, q_label, year, q_num, itr_data, dfp_data)
            if val is not None:
                grupo, label = SUMMARY_CODES.get(code, ("?", code))
                accounts.append({"codigo": code, "descricao": label, "grupo": grupo,
                                 "valor_brl": val})
        result_periods.append({
            "period": q_label,
            "year": year,
            "quarter": q_num,
            "accounts": accounts,
        })

    return {
        "status": "ok",
        "company": company_name,
        "period_type": "quarterly",
        "grupo_filter": grupo_filter or "all",
        "note": "Values are cumulative (not standalone) for flow statements.",
        "periods": result_periods,
    }


# ── Single-fetch: ALL statements in ONE SQL query ──────────────────────────

def _fetch_all_statements_annual(company, consolidado, periods) -> dict[str, dict]:
    """[v1.2] Fetch ALL statement codes in ONE SQL query, partition by grupo.

    Replaces 5 separate _fetch_complete_annual() calls (BPA/BPP/DRE/DFC/DVA)
    with a single query that fetches all key codes at once, then partitions
    the results by grupo in Python.

    Returns: {"BPA": {complete result}, "BPP": {complete result}, ...}
    Each value has the same structure as _fetch_complete_annual()'s return.
    """
    from skills.cvm.financials.metrics import KEY_CODES_BY_GRUPO

    # Build union of all codes + reverse lookup (code → grupo)
    all_codes: list[str] = []
    code_to_grupo: dict[str, str] = {}
    for grupo, codes in KEY_CODES_BY_GRUPO.items():
        for code in codes:
            if code not in code_to_grupo:
                all_codes.append(code)
                code_to_grupo[code] = grupo

    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        emp_ph = ",".join("?" * len(empresa_ids))
        code_ph = ",".join("?" * len(all_codes))

        # Query 1: discover target years (1 round-trip)
        year_rows = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                ORDER BY data_fim_exerc DESC LIMIT ?""",
            (*empresa_ids, *all_codes, consolidado, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found", "error": f"No data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        date_ph = ",".join("?" * len(target_dates))

        # Query 2: fetch ALL rows for ALL grupos (1 round-trip — replaces 5)
        rows = conn.execute(
            f"""SELECT codigo, descricao, grupo, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *all_codes, consolidado, *target_dates),
        ).fetchall()

        # Partition by grupo (using code_to_grupo mapping)
        by_grupo: dict[str, dict[str, list]] = {}
        for r in rows:
            grupo = code_to_grupo.get(r["codigo"])
            if not grupo:
                continue
            year_key = r["data_fim_exerc"][:4]
            if grupo not in by_grupo:
                by_grupo[grupo] = {}
            if year_key not in by_grupo[grupo]:
                by_grupo[grupo][year_key] = []
            escala = parse_escala(r["escala"])
            by_grupo[grupo][year_key].append({
                "codigo": r["codigo"],
                "descricao": r["descricao"],
                "grupo": r["grupo"],
                "valor_brl": float(r["valor"] or 0) * escala,
            })

        # Build complete-result dicts per grupo (same structure as _fetch_complete_annual)
        result: dict[str, dict] = {}
        for grupo, by_year in by_grupo.items():
            result[grupo] = {
                "status": "ok",
                "company": company_name,
                "period_type": "annual",
                "grupo_filter": grupo,
                "periods": [
                    {"year": y, "data_fim_exerc": f"{y}-12-31", "accounts": by_year[y]}
                    for y in sorted(by_year.keys(), reverse=True)
                ],
            }

        # Ensure all 5 grupos are present (even if empty)
        for grupo in KEY_CODES_BY_GRUPO:
            if grupo not in result:
                result[grupo] = {"status": "not_found", "error": f"No {grupo} data for '{company}'"}

        return result
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()


# ── Single-fetch: ALL statements for QUARTERLY periods ─────────────────────

def _fetch_all_statements_quarterly(
    company: str, consolidado: int, periods: int,
) -> dict[str, dict]:
    """[v1.24] Fetch ALL statement codes (from ``KEY_CODES_BY_GRUPO``) for
    quarterly periods via ITR + DFP, partitioned by grupo.

    Same return shape as ``_fetch_all_statements_annual()`` but with quarterly
    period labels like ``"2T2026"`` and STANDALONE flow values (DRE/DFC/DVA) —
    NOT cumulative.

    Logic:
      1. Resolve empresa_ids separately for DFP and ITR (separate DBs, IDs
         may differ — same P0 fix as ``_build_quarterly_summary``).
      2. Fetch ITR cumulative data (meses IN 3/6/9) for ALL key codes via
         ``_fetch_cumulative_full()`` (preserves ``descricao`` so the table
         can render official CVM labels).
      3. Fetch DFP annual data (meses=12) for the same codes — used for Q4.
      4. For each quarter (up to ``periods``, newest-first):
         - BPA/BPP (SNAPSHOT): direct period-end value (Q1-Q3 ITR, Q4 DFP).
         - DRE/DFC/DVA (FLOW):
           * Q1 (Jan-Mar): standalone = Q1 cumulative (fiscal year resets).
           * Q2 (Apr-Jun): standalone = ITR(meses=6) − ITR(meses=3).
           * Q3 (Jul-Sep): standalone = ITR(meses=9) − ITR(meses=6).
           * Q4 (Oct-Dec): standalone = DFP(meses=12) − ITR(meses=9).
      5. Return ``{"BPA": {...}, "BPP": {...}, "DRE": {...},
         "DFC_MI": {...}, "DVA": {...}}`` — same structure as annual.

    Args:
        company: ticker / name / CNPJ.
        consolidado: 1 for consolidated, 0 for individual.
        periods: max number of quarters to return (newest-first). Up to 20
            (5 years) — caller typically passes 20 for the dashboard's
            quarterly comparison tables.

    Returns:
        Per-grupo result dict. Each value has the same structure as
        ``_fetch_all_statements_annual()``'s per-grupo result, but
        ``period_type = "quarterly"`` and each period has
        ``{period, year, quarter, data_fim_exerc, accounts}`` where
        ``accounts`` is a list of ``{codigo, descricao, grupo, valor_brl}``
        dicts with STANDALONE values.
    """
    from skills.cvm.financials.metrics import KEY_CODES_BY_GRUPO

    # Build union of all codes + reverse lookup (code → grupo)
    all_codes: list[str] = []
    code_to_grupo: dict[str, str] = {}
    for grupo, codes in KEY_CODES_BY_GRUPO.items():
        for code in codes:
            if code not in code_to_grupo:
                all_codes.append(code)
                code_to_grupo[code] = grupo

    # ── Resolve empresa_ids SEPARATELY for DFP and ITR ───────────────────
    # DFP and ITR are separate SQLite files with independent autoincrement IDs.
    try:
        dfp_conn = connect_dfp(read_only=True)
        try:
            dfp_empresa_ids, company_name = resolve_company(dfp_conn, company)
            if not dfp_empresa_ids:
                return {"status": "not_found",
                        "error": f"Company '{company}' not found in DFP"}
        finally:
            dfp_conn.close()
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        itr_conn = connect_itr(read_only=True)
        try:
            itr_empresa_ids, _ = resolve_company(itr_conn, company)
        finally:
            itr_conn.close()
    except (FileNotFoundError, Exception):
        # ITR not synced — Q1-Q3 derivation will be incomplete, Q4 still works.
        itr_empresa_ids = []

    years_needed = (periods // 4) + 2  # current + prior + buffer

    # Fetch cumulative data WITH metadata (descricao, grupo)
    itr_data = _fetch_cumulative_full(
        itr_empresa_ids, consolidado, years_needed, "ITR", all_codes)
    dfp_data = _fetch_cumulative_full(
        dfp_empresa_ids, consolidado, years_needed, "DFP", all_codes)

    if not itr_data and not dfp_data:
        return {"status": "not_found",
                "error": f"No quarterly data found for '{company}'"}

    all_quarters = _build_quarter_labels(itr_data, dfp_data, periods)

    # Local value-getter helpers for the new dict shape
    # {year: {meses: {codigo: {"valor": float, "descricao": str, "grupo": str}}}}
    def _snap(code: str, year: int, q_num: int) -> float | None:
        """Snapshot/cumulative value: Q1-Q3 from ITR (meses 3/6/9), Q4 from DFP."""
        if q_num == 4:
            leaf = dfp_data.get(year, {}).get(12, {}).get(code)
        else:
            meses = {1: 3, 2: 6, 3: 9}[q_num]
            leaf = itr_data.get(year, {}).get(meses, {}).get(code)
        return leaf.get("valor") if leaf else None

    def _meta(code: str, year: int, q_num: int) -> dict:
        """Metadata (descricao, grupo) for a code at a given quarter."""
        if q_num == 4:
            return dfp_data.get(year, {}).get(12, {}).get(code) or {}
        meses = {1: 3, 2: 6, 3: 9}[q_num]
        return itr_data.get(year, {}).get(meses, {}).get(code) or {}

    def _prev_cum(code: str, year: int, q_num: int) -> float | None:
        """Previous quarter cumulative value (for standalone derivation).
        Q1 needs no prev (fiscal year resets). Q2→Q1, Q3→Q2, Q4→Q3 (all ITR).
        """
        if q_num == 1:
            return None
        prev_meses = {2: 3, 3: 6, 4: 9}[q_num]
        leaf = itr_data.get(year, {}).get(prev_meses, {}).get(code)
        return leaf.get("valor") if leaf else None

    # ── Build per-grupo, per-quarter accounts with STANDALONE values ─────
    by_grupo: dict[str, dict[str, list]] = {}
    for q_label, year, q_num in all_quarters:
        for code in all_codes:
            grupo = code_to_grupo[code]
            is_snapshot = grupo in ("BPA", "BPP")

            if is_snapshot:
                # Snapshot (balance sheet): direct period-end value
                val = _snap(code, year, q_num)
            else:
                # Flow (income/cash flow): derive standalone
                curr_cum = _snap(code, year, q_num)
                if curr_cum is None:
                    val = None
                elif q_num == 1:
                    # Q1 standalone = Q1 cumulative (fiscal year resets Jan 1)
                    val = curr_cum
                else:
                    prev_cum = _prev_cum(code, year, q_num)
                    val = (curr_cum - prev_cum) if prev_cum is not None else None

            if val is None:
                continue

            meta = _meta(code, year, q_num)
            descricao = meta.get("descricao") or code

            by_grupo.setdefault(grupo, {}).setdefault(q_label, []).append({
                "codigo": code,
                "descricao": descricao,
                "grupo": grupo,
                "valor_brl": val,
            })

    # Month-end date for each quarter (used for data_fim_exerc)
    month_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}

    # Build complete-result dicts per grupo (same structure as annual)
    result: dict[str, dict] = {}
    for grupo, by_quarter in by_grupo.items():
        result[grupo] = {
            "status": "ok",
            "company": company_name,
            "period_type": "quarterly",
            "grupo_filter": grupo,
            "periods": [
                {
                    "period": q_label,
                    "year": year,
                    "quarter": q_num,
                    "data_fim_exerc": f"{year}-{month_end[q_num]}",
                    "accounts": by_quarter.get(q_label, []),
                }
                for (q_label, year, q_num) in all_quarters
                if q_label in by_quarter
            ],
        }

    # Ensure all 5 grupos are present (even if empty)
    for grupo in KEY_CODES_BY_GRUPO:
        if grupo not in result:
            result[grupo] = {"status": "not_found",
                             "error": f"No {grupo} data for '{company}'"}

    return result
