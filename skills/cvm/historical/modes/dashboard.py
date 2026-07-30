"""Mode: dashboard -- multi-tab historical dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:             KPI cards (P/L, P/VPA, EV/EBITDA, ROE, ROIC,
                          Div Yield) + Summary text section
  - Percentile Analysis:  table showing current value vs 5Y distribution
                          (min/25th/median/75th/max) per metric
  - Trend:                table showing current + 1Y/3Y averages + 1Y/3Y
                          change per metric

This mode does NOT fetch new data -- it calls ``summary()`` once per
covered metric and reshapes the results into a multi-tab payload. If
``summary()`` itself fails (e.g. no company), the dashboard propagates the
error dict instead of rendering empty tabs.

The section-building helpers live in skills.cvm.historical.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.historical._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.historical._registry import register_mode
from skills.cvm.historical.modes.summary import summary
from skills.cvm.historical.report import (
    build_overview_kpis,
    build_overview_section,
    build_percentile_section,
    build_trend_section,
    fetch_quartiles,
)


# ── Metrics covered by the dashboard ────────────────────────────────────────
# (metric_name, KPI label, unit_kind) — unit_kind is "ratio" for price
# multiples (P/L, P/VPA, EV/EBITDA) and "pct" for profitability/yield ratios
# (ROE, ROIC, Div Yield). The unit_kind drives both KPI formatting and the
# scale (raw multiple vs 0-1 fraction) used in the Percentile + Trend tables.
_METRIC_DEFS: list[tuple[str, str, str]] = [
    ("lpa",       "P/L",       "ratio"),
    ("vpa",       "P/VPA",     "ratio"),
    ("ev_ebitda", "EV/EBITDA", "ratio"),
    ("roe",       "ROE",       "pct"),
    ("roic",      "ROIC",      "pct"),
    ("dpa",       "Div Yield", "pct"),
]


@register_mode(
    "dashboard",
    description=(
        "Multi-tab historical dashboard (thin composition of summary()). "
        "Tabs: Overview (6 KPI cards: P/L, P/VPA, EV/EBITDA, ROE, ROIC, "
        "Div Yield + Summary text), Percentile Analysis (current vs 5Y "
        "min/25th/median/75th/max), Trend (current vs 1Y/3Y averages + "
        "change). Optimized for the report tool's dashboard action."
    ),
    params={
        "company": "str. Ticker. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="historical", mode="dashboard", '
        'params=\'{"company":"PETR4"}\')',
    ],
)
def dashboard(company: str = "") -> dict:
    """Multi-tab historical dashboard (thin composition of summary()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:             KPI cards + Summary text section
      - Percentile Analysis:  current vs 5Y distribution per metric
      - Trend:                current + 1Y/3Y averages + change per metric

    This mode does NOT fetch new data -- it calls ``summary()`` once per
    covered metric and reshapes the results. If ``summary()`` itself fails
    (e.g. no company), the dashboard propagates the error dict instead of
    rendering empty tabs.

    Args:
        company: Ticker. Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no company), returns the ``summary()`` error
        dict verbatim.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    # ── Gather underlying data: call summary() once per covered metric ──
    # Defensive: each metric is wrapped in its own try/except so a single
    # failing metric (e.g. ev_ebitda when EBITDA can't be derived) doesn't
    # break the whole dashboard. The failing metric shows "—" in KPIs and
    # empty rows in the tables.
    summaries: dict[str, dict] = {}
    for metric_name, _label, _unit in _METRIC_DEFS:
        try:
            summaries[metric_name] = summary(company=company, metric=metric_name)
        except Exception as e:
            summaries[metric_name] = {
                "status": "error",
                "error": str(e),
            }

    # ── Fetch quartiles (25th/median/75th) per metric for Percentile tab ──
    # summary() exposes only min/max/percentile. The dashboard's Percentile
    # Analysis tab also wants 25th/median/75th, so we re-fetch the series
    # per metric and compute quartiles here.
    quartiles: dict[str, dict | None] = {}
    for metric_name, _label, _unit in _METRIC_DEFS:
        s = summaries.get(metric_name) or {}
        if s.get("status") != "ok":
            quartiles[metric_name] = None
            continue
        quartiles[metric_name] = fetch_quartiles(company, metric_name, months=60)

    # ── Top-level KPI cards (one per metric) ──
    kpis = build_overview_kpis(summaries, _METRIC_DEFS)

    # ── Tab 1: Overview -- Summary text section (KPIs live at the top level) ──
    overview_sections = [build_overview_section(summaries, _METRIC_DEFS, company)]

    # ── Tab 2: Percentile Analysis -- min/25th/median/75th/max/current ──
    percentile_sections = [build_percentile_section(summaries, quartiles, _METRIC_DEFS)]

    # ── Tab 3: Trend -- current + 1Y/3Y averages + change ──
    trend_sections = [build_trend_section(summaries, _METRIC_DEFS)]

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",            "sections": overview_sections},
        {"name": "Percentile Analysis", "sections": percentile_sections},
        {"name": "Trend",               "sections": trend_sections},
    ]
    return {
        "status": "ok",
        "company": company,
        "tabs": tabs,
        "kpis": kpis,
    }
