"""skills/cvm/comparison/comparison.py -- Compare N tickers across CVM skills.

Calls the existing financials + valuation + dividends skills internally per
ticker (best-effort — a ticker missing from one source doesn't fail the whole
comparison) and merges into a side-by-side structure.

MODES
-----
  side_by_side (default) -- 3 sections (valuation, financials, dividends).
                            Each section: rows = tickers, columns = metrics.
  summary                -- single quick-compare table (10 KPIs).
  growth                 -- QoQ + YoY % change for Receita, EBITDA, Lucro Líquido.

CALCULATIONS INTEGRATION (v1.3)
-------------------------------
Since Phase 2B, valuation.ratios() returns ~10 additional ratios computed by
the calculations engines (roe, roa, margem_bruta, margem_operacional,
margem_liquida, divida_pl, giro_ativos, liquidez_corrente, roic,
graham_number, p_ebit, p_fco, p_fcf). Comparison picks these up transitively
via the existing `entry["valuation"] = r.get("ratios", {})` line in
`_fetch_all()` — no new data fetching required. The v1.3 update just adds
column definitions in `_VALUATION_COLS` so the new metrics render in the
valuation section of `side_by_side()`.

NO SYNC
-------
Read-only. Calls the existing CVM skills (which call data_source query engines).
Assumes dfp.db + itr.db + fre.db + bridge.db + b3 dividends.db are synced.
"""

from __future__ import annotations

from typing import Any


# ── Valuation columns (from valuation.ratios) ────────────────────────────────
# Each is (column_name, ratios_key, spec). Multiples use "num", BRL uses "brl",
# fractions use "pct".
# [v1.3] Added ROE, ROA, Marg. Líquida, Dívida/PL, Liquidez Corrente — these
# are returned directly by valuation.ratios() since Phase 2B (calculations
# metrics roe_at, roa_at, net_margin_at, debt_equity_at, current_ratio_at are
# composed inside valuation.ratios and exposed in the ratios dict). The same
# metrics also appear in the financials section (computed by compute_ratios
# from the raw statement dict); the valuation column shows the calculations
# engine value (point-in-time TTM snapshot), the financials column shows the
# annual statement value. Both are useful — they cross-check each other.
_VALUATION_COLS = [
    ("Preço",            "price",            "brl_full"),
    ("Market Cap",       "market_cap",       "brl"),
    ("EV",               "ev",               "brl"),
    ("P/L",              "p_l",              "num"),
    ("P/VPA",            "p_vpa",            "num"),
    ("P/EBIT",           "p_ebit",           "num"),
    ("EV/EBITDA",        "ev_ebitda",        "num"),
    ("PSR",              "psr",              "num"),
    ("Div Yield",        "dividend_yield",   "pct"),
    ("DPA",              "dpa",              "brl_full"),
    ("EPS",              "eps",              "brl_full"),
    ("VPA",              "vpa",              "brl_full"),
    ("Total Ações",      "total_shares",     "int"),
    # [v1.3] New — calculations metrics surfaced via valuation.ratios()
    ("ROE (val)",        "roe",              "pct"),
    ("ROA (val)",        "roa",              "pct"),
    ("Marg. Líq. (val)", "margem_liquida",   "pct"),
    ("Dívida/PL",        "divida_pl",        "num"),
    ("Liquidez Corrente","liquidez_corrente","num"),
]

# ── Financials columns (from financials.summary -> latest_annual) ────────────
_FINANCIALS_COLS = [
    ("Receita Líquida",  "receita_liquida",      "brl"),
    ("Lucro Bruto",      "lucro_bruto",          "brl"),
    ("EBIT",             "ebit",                 "brl"),
    ("EBITDA",           "ebitda",               "brl"),
    ("Lucro Líquido",    "lucro_liquido",        "brl"),
    ("Ativo Total",      "ativo_total",          "brl"),
    ("Patrimônio Líq.",  "patrimonio_liquido",   "brl"),
    ("Caixa",            "caixa",                "brl"),
    ("Dívida Bruta",     "divida_bruta",         "brl"),
    ("FCO",              "fco",                  "brl"),
    ("Marg. Bruta",      "marg_bruta",           "pct"),
    ("Marg. EBITDA",     "marg_ebitda",          "pct"),
    ("Marg. Líquida",    "marg_liquida",         "pct"),
    ("ROE",              "roe",                  "pct"),
    ("ROA",              "roa",                  "pct"),
    ("Payout",           "payout",               "pct"),
]

# ── Dividends columns (from dividends.summary) ───────────────────────────────
# DPA + Div Yield here come from the dividends skill (B3 history + DVA), which
# may differ slightly from valuation's (price-based) — both are useful context.
_DIVIDENDS_COLS = [
    ("Eventos (B3)",         "event_count",      "int"),
    ("DPA (B3 médio)",       "b3_dpa_avg",       "brl_full"),
    ("Dividendos (últ ano)", "annual_dividendos", "brl"),
    ("JCP (últ ano)",        "annual_jcp",        "brl"),
    ("Total Remun. (últ a)", "annual_total",      "brl"),
]

# ── Summary mode: the ~10 KPIs for quick compare ─────────────────────────────
_SUMMARY_COLS = [
    ("Preço",         "price",          "brl_full"),
    ("Market Cap",    "market_cap",     "brl"),
    ("P/L",           "p_l",            "num"),
    ("P/VPA",         "p_vpa",          "num"),
    ("EV/EBITDA",     "ev_ebitda",      "num"),
    ("ROE",           "roe",            "pct"),
    ("Div Yield",     "dividend_yield", "pct"),
    ("Receita Líquida","receita_liquida","brl"),
    ("EBITDA",        "ebitda",         "brl"),
    ("Lucro Líquido", "lucro_liquido",  "brl"),
]

# ── Growth mode: QoQ + YoY % change ──────────────────────────────────────────
# Each entry: (column_label, dict_key, spec). dict_key is looked up in the
# growth dict returned by _compute_growth().
_GROWTH_COLS = [
    ("Receita QoQ",    "receita_qoq",    "pct_raw"),
    ("Receita YoY",    "receita_yoy",    "pct_raw"),
    ("EBITDA QoQ",     "ebitda_qoq",     "pct_raw"),
    ("EBITDA YoY",     "ebitda_yoy",     "pct_raw"),
    ("Lucro Liq. QoQ", "lucro_qoq",      "pct_raw"),
    ("Lucro Liq. YoY", "lucro_yoy",      "pct_raw"),
    ("Marg. EBITDA",   "marg_ebitda",    "pct"),
    ("ROE (TTM)",      "roe_ttm",        "pct"),
]


# ── Mode: side_by_side (default) ─────────────────────────────────────────────

def side_by_side(tickers: list = None, consolidado: int = 1) -> dict:
    """Compare N tickers across 3 sections (valuation, financials, dividends).

    Args:
        tickers: List of B3 tickers, e.g. ["PETR4","VALE3"]. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    per_ticker = _fetch_all(tickers, consolidado)

    # [v1.2] Sector tagging — resolve each ticker's sector from CAD
    sectors = _fetch_sectors(tickers)

    sections = {
        "valuation":   _build_section("Valuation Ratios", _VALUATION_COLS,
                                      [t["valuation"] for t in per_ticker], tickers),
        "financials":  _build_section("Financial Metrics (latest annual)", _FINANCIALS_COLS,
                                      [t["financials"] for t in per_ticker], tickers),
        "dividends":   _build_section("Dividend Metrics", _DIVIDENDS_COLS,
                                      [t["dividends"] for t in per_ticker], tickers),
    }

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": sections,
        "errors": [t["error"] for t in per_ticker if t["error"]],
    }


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(tickers: list = None, consolidado: int = 1) -> dict:
    """Single quick-compare table: 1 row per ticker, ~10 KPI columns.

    Args:
        tickers: List of B3 tickers. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    per_ticker = _fetch_all(tickers, consolidado)

    # Merge valuation + financials ratios into a single row per ticker
    merged = []
    for t in per_ticker:
        row = dict(t["valuation"])          # price, p_l, market_cap, ...
        row.update(t["financials"])         # receita, ebitda, roe, ...
        row.update(t["dividends"])          # dividend_yield (from valuation), event_count, ...
        merged.append(row)

    section = _build_section("Quick Compare", _SUMMARY_COLS, merged, tickers)

    # [v1.2] Sector tagging
    sectors = _fetch_sectors(tickers)

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": [section],
        "errors": [t["error"] for t in per_ticker if t["error"]],
    }


# ── Mode: growth ─────────────────────────────────────────────────────────────

def growth(tickers: list = None, consolidado: int = 1) -> dict:
    """Compare N tickers on growth metrics: QoQ + YoY % change + TTM ratios.

    Calls financials.quarterly(periods=8) per ticker to get standalone quarters,
    then computes QoQ (latest vs prior) and YoY (latest vs same quarter prior
    year) growth for Receita, EBITDA, Lucro Líquido. Also includes TTM
    Marg. EBITDA and ROE from the financials skill's TTM summary.

    Args:
        tickers: List of B3 tickers. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    from skills.cvm.financials.financials import quarterly as fin_quarterly

    growth_data = []
    errors = []
    for ticker in tickers:
        try:
            r = fin_quarterly(company=ticker, periods=8, consolidado=consolidado)
            if r.get("status") == "ok":
                growth_data.append(_compute_growth(r))
            else:
                growth_data.append({})
                errors.append(f"{ticker}: financials: {r.get('error', r.get('status', ''))}")
        except Exception as e:
            growth_data.append({})
            errors.append(f"{ticker}: financials: {e}")

    section = _build_section("Growth Metrics (QoQ + YoY + TTM)", _GROWTH_COLS,
                             growth_data, tickers)

    # [v1.2] Sector tagging
    sectors = _fetch_sectors(tickers)

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": [section],
        "errors": errors,
    }


def _compute_growth(financials_result: dict) -> dict:
    """Compute QoQ + YoY growth + TTM ratios from a financials.quarterly result.

    QoQ = (latest_quarter - prior_quarter) / |prior_quarter|
    YoY = (latest_quarter - same_quarter_last_year) / |same_quarter_last_year|

    Returns a flat dict with keys matching _GROWTH_COLS.
    """
    periods = financials_result.get("periods") or []
    ttm = financials_result.get("ttm") or {}

    out = {
        "receita_qoq": None, "receita_yoy": None,
        "ebitda_qoq": None, "ebitda_yoy": None,
        "lucro_qoq": None, "lucro_yoy": None,
        "marg_ebitda": None, "roe_ttm": None,
    }

    if not periods:
        return out

    # Sort newest-first by (year, quarter)
    sorted_p = sorted(periods,
                      key=lambda p: (p.get("year", 0), p.get("quarter", 0)),
                      reverse=True)

    latest = sorted_p[0] if sorted_p else {}
    latest_m = latest.get("metrics", {}) or {}

    # QoQ: latest vs the one right before it
    prior = sorted_p[1] if len(sorted_p) > 1 else {}
    prior_m = prior.get("metrics", {}) or {}

    out["receita_qoq"] = _pct_change(latest_m.get("receita_liquida"),
                                      prior_m.get("receita_liquida"))
    out["ebitda_qoq"] = _pct_change(latest_m.get("ebitda"),
                                     prior_m.get("ebitda"))
    out["lucro_qoq"] = _pct_change(latest_m.get("lucro_liquido"),
                                    prior_m.get("lucro_liquido"))

    # YoY: latest vs same quarter prior year (4 periods back)
    yoy_prior = sorted_p[4] if len(sorted_p) > 4 else {}
    yoy_m = yoy_prior.get("metrics", {}) or {}

    out["receita_yoy"] = _pct_change(latest_m.get("receita_liquida"),
                                      yoy_m.get("receita_liquida"))
    out["ebitda_yoy"] = _pct_change(latest_m.get("ebitda"),
                                     yoy_m.get("ebitda"))
    out["lucro_yoy"] = _pct_change(latest_m.get("lucro_liquido"),
                                    yoy_m.get("lucro_liquido"))

    # TTM ratios from the financials skill's TTM summary
    ttm_ratios = ttm.get("ratios", {}) or {}
    out["marg_ebitda"] = ttm_ratios.get("marg_ebitda")
    out["roe_ttm"] = ttm_ratios.get("roe")

    return out


def _pct_change(curr: float | None, prev: float | None) -> float | None:
    """Compute % change = (curr - prev) / |prev|.

    Returns None only when:
    - either value is None
    - prev is 0 or negative (can't compute meaningful % from non-positive base)
    - curr and prev have opposite signs (profit→loss or loss→profit — % is
      meaningless across a sign change)

    Extreme values (>500%) are NOT suppressed — they may be real (e.g. a company
    recovering from a tiny-base quarter). The LLM can judge whether the growth
    is meaningful. The sign-change guard alone catches the truly meaningless
    cases (the 3612% / -395% noise from v1.1 was caused by sign changes, not
    just magnitude).
    """
    if curr is None or prev is None:
        return None
    if prev <= 0:
        return None
    # Sign change: profit→loss or loss→profit — % growth is meaningless
    if curr * prev < 0:
        return None
    return (curr - prev) / abs(prev)


# ── Internal: fetch sectors from CAD ─────────────────────────────────────────

def _fetch_sectors(tickers: list[str]) -> dict[str, str]:
    """Resolve each ticker's sector (SETOR_ATIV) from CAD via bridge → CNPJ.

    Returns {ticker: sector_string}. Best-effort — missing sectors are "".
    """
    sectors = {}
    try:
        from data_sources.cvm.cad.query_engine import lookup as cad_lookup
        from data_sources.cvm._bridge import _resolve_via_bridge
    except ImportError:
        return {t: "" for t in tickers}

    for ticker in tickers:
        try:
            cnpj, _ = _resolve_via_bridge(ticker)
            if not cnpj:
                sectors[ticker] = ""
                continue
            r = cad_lookup(cnpj=cnpj)
            if r.get("status") == "ok":
                sectors[ticker] = (r.get("company") or {}).get("SETOR_ATIV", "") or ""
            else:
                sectors[ticker] = ""
        except Exception:
            sectors[ticker] = ""
    return sectors


# ── Internal: fetch all 3 skills per ticker (best-effort) ────────────────────

def _fetch_all(tickers: list[str], consolidado: int) -> list[dict]:
    """For each ticker, call the 3 skills best-effort. Never raises.

    Returns a list (aligned with tickers) of:
        {ticker, valuation: {}, financials: {}, dividends: {}, error: str?}
    Each metric dict may be partial (missing keys = None downstream).
    """
    from skills.cvm.financials.financials import summary as fin_summary
    from skills.cvm.valuation.valuation import ratios as val_ratios
    from skills.cvm.dividends.dividends import summary as div_summary

    out = []
    for ticker in tickers:
        entry: dict[str, Any] = {
            "ticker": ticker,
            "valuation": {},
            "financials": {},
            "dividends": {},
            "error": "",
        }

        # 1. Valuation (ratios mode)
        try:
            r = val_ratios(company=ticker)
            if r.get("status") == "ok":
                entry["valuation"] = r.get("ratios", {}) or {}
            else:
                entry["error"] = f"valuation: {r.get('error', r.get('status',''))}"
        except Exception as e:
            entry["error"] = f"valuation: {e}"

        # 2. Financials (summary mode -> latest_annual metrics + ratios)
        try:
            r = fin_summary(company=ticker, consolidado=consolidado)
            if r.get("status") == "ok":
                sections = r.get("sections", {}) or {}
                latest_annual = sections.get("latest_annual") or {}
                if latest_annual.get("status") == "ok" or latest_annual.get("metrics"):
                    m = latest_annual.get("metrics", {}) or {}
                    ratios = latest_annual.get("ratios", {}) or {}
                    # Flatten metrics + ratios into one dict for column lookup
                    entry["financials"] = {**m, **ratios}
                else:
                    if not entry["error"]:
                        entry["error"] = f"financials: {latest_annual.get('error','no data')}"
            else:
                if not entry["error"]:
                    entry["error"] = f"financials: {r.get('error', r.get('status',''))}"
        except Exception as e:
            if not entry["error"]:
                entry["error"] = f"financials: {e}"

        # 3. Dividends (summary mode)
        try:
            r = div_summary(company=ticker)
            if r.get("status") == "ok":
                entry["dividends"] = _extract_dividend_metrics(r.get("sections", {}) or {})
            else:
                if not entry["error"]:
                    entry["error"] = f"dividends: {r.get('error', r.get('status',''))}"
        except Exception as e:
            if not entry["error"]:
                entry["error"] = f"dividends: {e}"

        out.append(entry)
    return out


def _extract_dividend_metrics(sections: dict) -> dict:
    """Pull flat dividend metrics from the dividends.summary sections.

    Returns: {event_count, b3_dpa_avg, annual_dividendos, annual_jcp,
              annual_total, payout}
    """
    out = {
        "event_count": None, "b3_dpa_avg": None,
        "annual_dividendos": None, "annual_jcp": None,
        "annual_total": None, "payout": None,
    }

    # Recent events (B3)
    re_block = sections.get("recent_events") or {}
    if re_block.get("status") == "ok" or re_block.get("events"):
        events = re_block.get("events") or []
        out["event_count"] = re_block.get("count", len(events))
        if events:
            rates = [e.get("rate") for e in events if e.get("rate") is not None]
            if rates:
                out["b3_dpa_avg"] = sum(rates) / len(rates)

    # Annual trend (DVA) — latest year
    at_block = sections.get("annual_trend") or {}
    if at_block.get("status") == "ok" or at_block.get("periods"):
        periods = at_block.get("periods") or []
        if periods:
            latest = periods[0]
            accounts = latest.get("accounts") or {}
            out["annual_dividendos"] = (accounts.get("7.08.04.02") or {}).get("valor_brl")
            out["annual_jcp"] = (accounts.get("7.08.04.01") or {}).get("valor_brl")
            out["annual_total"] = (accounts.get("7.08.04") or {}).get("valor_brl")

    return out


# ── Internal: build a section from per-ticker dicts ──────────────────────────

def _build_section(title: str, cols: list[tuple], per_ticker: list[dict],
                   tickers: list[str]) -> dict:
    """Build a section: rows = tickers, columns = metric labels.

    cols: list of (column_label, dict_key, spec)
    per_ticker: list of dicts (one per ticker) to look up dict_key in
    tickers: list of ticker labels for the first column
    """
    columns = ["Ticker"] + [label for label, _key, _spec in cols]
    rows = []
    for ticker, data in zip(tickers, per_ticker):
        row = [ticker]
        for _label, key, _spec in cols:
            row.append(data.get(key))
        rows.append(row)
    formats = {"Ticker": "text"}
    for label, _key, spec in cols:
        formats[label] = spec
    return {
        "title": title,
        "columns": columns,
        "rows": rows,
        "formats": formats,
    }
