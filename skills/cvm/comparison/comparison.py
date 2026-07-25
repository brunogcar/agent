"""skills/cvm/comparison/comparison.py -- Compare N tickers across CVM skills.

Calls the existing financials + valuation + dividends skills internally per
ticker (best-effort — a ticker missing from one source doesn't fail the whole
comparison) and merges into a side-by-side structure.

MODES
-----
  side_by_side (default) -- 3 sections (valuation, financials, dividends).
                            Each section: rows = tickers, columns = metrics.
  summary                -- single quick-compare table (10 KPIs).

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
_VALUATION_COLS = [
    ("Preço",         "price",            "brl_full"),
    ("Market Cap",    "market_cap",       "brl"),
    ("EV",            "ev",               "brl"),
    ("P/L",           "p_l",              "num"),
    ("P/VPA",         "p_vpa",            "num"),
    ("P/EBIT",        "p_ebit",           "num"),
    ("EV/EBITDA",     "ev_ebitda",        "num"),
    ("PSR",           "psr",              "num"),
    ("Div Yield",     "dividend_yield",   "pct"),
    ("DPA",           "dpa",              "brl_full"),
    ("EPS",           "eps",              "brl_full"),
    ("VPA",           "vpa",              "brl_full"),
    ("Total Ações",   "total_shares",     "int"),
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
    ("Payout",               "payout",            "pct"),
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

    return {
        "status": "ok",
        "tickers": tickers,
        "sections": [section],
        "errors": [t["error"] for t in per_ticker if t["error"]],
    }


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
