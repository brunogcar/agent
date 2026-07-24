"""skills/cvm/financials/financials.py -- Financial statements skill.

Combines DFP (annual) + ITR (quarterly cumulative) + B3 dividends + DVA to
produce rapina-style financial summaries with standalone quarters + ratios.

MODES
-----
  quarterly (default) — standalone quarters + ratios, default 8 quarters
  annual              — annual summary + ratios, default 5 years
  complete            — full statements by grupo + key account codes
  summary             — combined latest annual + latest quarterly + key ratios

STANDALONE QUARTER DERIVATION
-----------------------------
ITR stores cumulative (Q1=3meses, Q2=6, Q3=9). Standalone:
  Q1 = cum3 (ITR)
  Q2 = cum6 (ITR) - cum3
  Q3 = cum9 (ITR) - cum6
  Q4 = DFP annual (meses=12) - cum9 (ITR)
Snapshots (BPA/BPP) use period-end value directly (no subtraction).

NO SYNC
-------
Read-only. Assumes dfp.db + itr.db + (optional) dividends.db are synced.
"""

from __future__ import annotations

from typing import Any

from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala, cnpj_digits
from data_sources.cvm._bridge import resolve_company
from skills.cvm.financials.metrics import (
    SUMMARY_CODES, KEY_CODES_BY_GRUPO,
    compute_ratios, compute_ebitda, compute_ttm_ebitda,
    _f,
)


# ── Mode: quarterly (default) ────────────────────────────────────────────────

def quarterly(company: str = "", periods: int = 8, consolidado: int = 1) -> dict:
    """Standalone quarterly summary + ratios (default 8 quarters).

    Derives standalone quarters from ITR cumulative + DFP annual.
    Computes: margins, EBITDA, ROA/ROE (annualized), debt ratios, payout.

    Args:
        company: Ticker, name, or CNPJ.
        periods: Number of quarters. Default: 8.
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    return _build_summary(company, periods, consolidado, is_quarterly=True)


# ── Mode: annual ─────────────────────────────────────────────────────────────

def annual(company: str = "", periods: int = 5, consolidado: int = 1) -> dict:
    """Annual summary + ratios (default 5 years).

    Queries DFP annual values (meses=12) + DVA for proventos.
    Computes: margins, EBITDA, ROA/ROE, debt ratios, payout.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    return _build_summary(company, periods, consolidado, is_quarterly=False)


# ── Mode: complete ───────────────────────────────────────────────────────────

def complete(
    company: str = "",
    period: str = "quarterly",
    grupo: str = "",
    consolidado: int = 1,
    periods: int = 8,
) -> dict:
    """Full statements by grupo + key account codes (not all 497).

    Args:
        company: Ticker, name, or CNPJ.
        period: "quarterly" (default) or "annual".
        grupo: Statement group filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes.
        consolidado: 1=consolidated, 0=individual.
        periods: Number of periods. Default: 8 (quarterly) or 5 (annual).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    period = period.strip().lower()
    if period not in ("quarterly", "annual"):
        return {"status": "error", "error": f"period must be 'quarterly' or 'annual', got '{period}'"}

    # Determine which codes to fetch
    if grupo:
        grupo = grupo.strip().upper()
        if grupo not in KEY_CODES_BY_GRUPO:
            return {"status": "error",
                    "error": f"Unknown grupo '{grupo}'. Available: {list(KEY_CODES_BY_GRUPO.keys())}"}
        codes_to_fetch = KEY_CODES_BY_GRUPO[grupo]
    else:
        # All key codes from all grupos
        codes_to_fetch = []
        for codes in KEY_CODES_BY_GRUPO.values():
            codes_to_fetch.extend(codes)
        codes_to_fetch = list(set(codes_to_fetch))

    if period == "quarterly":
        return _fetch_complete_quarterly(company, codes_to_fetch, grupo, consolidado, periods)
    else:
        return _fetch_complete_annual(company, codes_to_fetch, grupo, consolidado, periods)


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "", consolidado: int = 1) -> dict:
    """Combined: latest annual + latest quarterly + key ratios.

    Best-effort — if one data source is missing, returns what's available.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    result: dict[str, Any] = {"status": "ok", "company": company, "sections": {}}

    # Latest annual (1 year)
    try:
        ann = annual(company=company, periods=1, consolidado=consolidado)
        if ann.get("status") == "ok" and ann.get("periods"):
            result["sections"]["latest_annual"] = ann["periods"][0]
        else:
            result["sections"]["latest_annual"] = {"status": ann.get("status"),
                                                   "error": ann.get("error", "")}
    except Exception as e:
        result["sections"]["latest_annual"] = {"status": "error", "error": str(e)}

    # Latest quarterly (4 quarters for context)
    try:
        qrt = quarterly(company=company, periods=4, consolidado=consolidado)
        if qrt.get("status") == "ok" and qrt.get("periods"):
            # [v1.0.1 P1 fix] periods are sorted oldest-first, so latest = periods[-1]
            result["sections"]["latest_quarterly"] = qrt["periods"][-1]
            result["sections"]["quarterly_trend"] = qrt["periods"]
        else:
            result["sections"]["latest_quarterly"] = {"status": qrt.get("status"),
                                                       "error": qrt.get("error", "")}
    except Exception as e:
        result["sections"]["latest_quarterly"] = {"status": "error", "error": str(e)}

    return result


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
            "period_type": "quarterly", "periods": result_periods}


# ── Internal: data fetching helpers ──────────────────────────────────────────

def _fetch_quarterly_cumulative(
    empresa_ids: list[int],
    consolidado: int,
    years_needed: int,
    source: str,
) -> dict:
    """Fetch cumulative quarterly data from ITR or annual from DFP.

    Returns: {year: {meses: {codigo: valor}}} for the given source.
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
            (*empresa_ids, *codes, consolidado, years_needed * len(codes) * 4),
        ).fetchall()
    except FileNotFoundError:
        return {}
    finally:
        conn.close()

    # Organize: {year: {meses: {codigo: valor}}}
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
    """Extract named metrics from a {codigo: valor} dict."""
    divida_bruta = None
    d_circ = _f(vals, "2.01.04")
    d_ncirc = _f(vals, "2.02.01")
    if d_circ is not None or d_ncirc is not None:
        divida_bruta = (d_circ or 0) + (d_ncirc or 0)

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
        "da":                   _f(vals, "6.01.01.02"),
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
