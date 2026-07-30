"""skills/cvm/comparison/fetchers.py -- Cross-skill fetchers + section builder.

Two responsibilities:

1. Fetch comparison data from the 3 underlying skills (financials + valuation
   + dividends) per ticker — best-effort, never raises. Used by side_by_side,
   summary, dashboard modes.

2. Build comparison "section" dicts from per-ticker metric dicts — used by
   side_by_side, summary, growth, dashboard modes. A section is the generic
   table shape consumed by the report adapters:
       {title, columns, rows, formats}

Sector resolution (_fetch_sectors) is included here because it shares the
bridge → CAD lookup path with the financials fetcher.
"""
from __future__ import annotations

from typing import Any


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
    from skills.cvm.financials.modes.summary import summary as fin_summary
    from skills.cvm.valuation.modes.ratios import ratios as val_ratios
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
