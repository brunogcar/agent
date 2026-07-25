"""adapters/screener.py — Flatten screener skill JSON → table data.

Adapter:
  screener_sector — sector peers table (sorted by P/L cheapest-first) + KPIs
                    showing sector medians.

Usage:
  report(action="table", title="Papel e Celulose Sector",
         data=<screener sector JSON>, config={"adapter":"screener_sector"})
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table
from tools.report_ops.formats import apply_fmt


_PEER_COLS = [
    ("Ticker",        "ticker",          "text"),
    ("Preço",         "price",           "brl_full"),
    ("Market Cap",    "market_cap",      "brl"),
    ("P/L",           "p_l",             "num"),
    ("P/VPA",         "p_vpa",           "num"),
    ("EV/EBITDA",     "ev_ebitda",       "num"),
    ("ROE",           "roe",             "pct"),
    ("Div Yield",     "dividend_yield",  "pct"),
    ("Receita Líquida", "receita_liquida", "brl"),
    ("EBITDA",        "ebitda",          "brl"),
    ("Lucro Líquido", "lucro_liquido",   "brl"),
    ("Marg. EBITDA",  "marg_ebitda",     "pct"),
    ("Marg. Líquida", "marg_liquida",    "pct"),
    ("Cresc. Receita","receita_growth",  "pct"),
    ("Payout",        "payout",          "pct"),
]


@register_adapter("screener_sector")
def sector(result: dict) -> dict:
    """Flatten screener.sector result into a peers table + median KPIs."""
    if not _ok(result):
        return _error_table(result, title="Sector Screener")

    peers = result.get("peers") or []
    medians = result.get("medians") or {}
    setor = result.get("setor", "")

    if not peers:
        return _error_table(result, title=f"Sector: {setor}")

    # Build the peers table
    columns = [label for label, _key, _spec in _PEER_COLS]
    rows = []
    for p in peers:
        row = []
        for _label, key, _spec in _PEER_COLS:
            row.append(p.get(key))
        rows.append(row)
    formats = {label: spec for label, _key, spec in _PEER_COLS}

    section = {
        "title": f"Sector: {setor} ({len(peers)} peers, sorted by P/L cheapest-first)",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": f"Peer count: {result.get('peer_count', len(peers))}. "
                f"Errors: {len(result.get('errors', []))} companies skipped.",
    }

    # KPI strip: sector medians
    kpis = [
        {"label": "Median P/L", "value": medians.get("p_l"), "format": "num"},
        {"label": "Median P/VPA", "value": medians.get("p_vpa"), "format": "num"},
        {"label": "Median EV/EBITDA", "value": medians.get("ev_ebitda"), "format": "num"},
        {"label": "Median ROE", "value": medians.get("roe"), "format": "pct"},
        {"label": "Median Div Yield", "value": medians.get("dividend_yield"), "format": "pct"},
    ]

    return {
        "company": setor,
        "sections": [section],
        "kpis": kpis,
        "sources": [],
    }
