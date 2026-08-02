"""Mode: historical_valuation -- historical valuation multiples time series.

[v1.8] New. Mirrors the financials TTM mode pattern, but for valuation
multiples. Fetches 5Y of daily history for key valuation metrics
(P/L, P/VPA, EV/EBITDA, EV/EBIT, EV/Sales, Earnings Yield) via the
calculations registry's *_history() functions.

Produces a time series that can be charted as line charts showing
how the company's valuation multiples have evolved over time — useful
for "is P/L cheap vs its own history?" analysis.

Registered as "historical_valuation" in skills.cvm.valuation._registry.MODES
via the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from datetime import date, timedelta

from skills.cvm.valuation._registry import register_mode


# Metrics to include in the historical series. Each entry is:
# (display_label, history_fn_name, module_path, history_key)
# history_key is the key in each history entry that holds the value.
_HISTORICAL_METRICS = [
    ("EV/EBITDA",       "ev_ebitda_history",      "skills.cvm.calculations.metrics.ev_ebitda",      "ev_ebitda"),
    ("EV/EBIT",         "ev_ebit_history",        "skills.cvm.calculations.metrics.ev_ebit",        "ev_ebit"),
    ("EV/Sales",        "ev_sales_history",       "skills.cvm.calculations.metrics.ev_sales",       "ev_sales"),
    ("P/EBIT",          "p_ebit_history",         "skills.cvm.calculations.metrics.p_ebit",         "p_ebit"),
    ("P/EBITDA",        "p_ebitda_history",       "skills.cvm.calculations.metrics.p_ebitda",       "p_ebitda"),
    ("Earnings Yield",  "earnings_yield_history", "skills.cvm.calculations.metrics.earnings_yield",  "earnings_yield"),
    ("Graham Number",   "graham_number_history",  "skills.cvm.calculations.metrics.graham_number",  "graham_number"),
    ("ROE",             "roe_history",            "skills.cvm.calculations.metrics.roe",            "roe"),
    ("ROIC",            "roic_history",           "skills.cvm.calculations.metrics.roic",           "roic"),
]


@register_mode(
    "historical_valuation",
    description=(
        "Historical valuation multiples time series (5Y default). "
        "Fetches daily history for P/L, P/VPA, EV/EBITDA, EV/EBIT, "
        "EV/Sales, Earnings Yield, Graham Number, ROE, ROIC via the "
        "calculations registry's *_history() functions. Useful for "
        "'is P/L cheap vs its own history?' analysis."
    ),
    params={
        "company": "str. B3 ticker (PETR4). Required.",
        "years":   "int. Number of years of history. Default: 5.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="valuation", mode="historical_valuation", params=\'{"company":"PETR4"}\')',
    ],
)
def historical_valuation(company: str = "", years: int = 5) -> dict:
    """Historical valuation multiples time series.

    Fetches `years` years of daily history for key valuation metrics
    via the calculations registry's *_history() functions. Each metric's
    history function returns a list of ``{"date": str, "<key>": float}``
    dicts — this mode merges them into a unified time series keyed by date.

    Args:
        company: Ticker, name, or CNPJ.
        years: Number of years of history. Default: 5.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "metrics": [...],
        "series": {...}}`` where:
        - ``metrics`` is a list of ``{"label", "key"}`` for charting.
        - ``series`` is a dict ``{date_str: {metric_key: value, ...}}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[valuation] Historical: Fetching {years}Y history for {company}...", flush=True)

    today = date.today()
    date_from = (today - timedelta(days=365 * years)).isoformat()
    date_to = today.isoformat()

    # Import + call each metric's history function.
    # Use engine_cache_scope for shared engine caching across metrics.
    from skills._base import engine_cache_scope

    metric_defs: list[dict] = []
    all_series: dict[str, dict[str, float | None]] = {}  # {date: {key: value}}

    with engine_cache_scope():
        for label, fn_name, module_path, history_key in _HISTORICAL_METRICS:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                fn = getattr(mod, fn_name)
                print(f"[valuation] Historical:   {label}...", flush=True, end="")
                series = fn(company, date_from, date_to)
                print(f" {len(series)} points.", flush=True)

                metric_defs.append({"label": label, "key": history_key})

                # Merge into all_series: {date: {key: value}}
                for point in series:
                    d = point.get("date", "")
                    if not d:
                        continue
                    if d not in all_series:
                        all_series[d] = {"date": d}
                    val = point.get(history_key)
                    if val is not None:
                        all_series[d][history_key] = val
            except Exception as e:
                print(f" error: {e}", flush=True)
                metric_defs.append({"label": label, "key": history_key, "error": str(e)})

    # Sort by date.
    sorted_dates = sorted(all_series.keys())
    series_list = [all_series[d] for d in sorted_dates]

    print(f"[valuation] Historical: Done! {len(series_list)} dates, {len(metric_defs)} metrics.", flush=True)

    return {
        "status": "ok",
        "company": company,
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metric_defs,
        "series": series_list,
    }
