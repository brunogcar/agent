"""Mode: dashboard -- multi-tab historical dashboard (thin composition mode).

[v2.1] Reorganized from 3 tabs to 5 tabs with charts, ratio_grid, subtabs:
  - Overview:             KPI cards + Summary text section
  - Valuation:            subtabs (Percentile table + bar chart, Trend table)
                          for valuation metrics (P/L, P/VPA, EV/EBITDA)
  - Profitability:        subtabs (Percentile table + bar chart, Trend table)
                          for profitability metrics (ROE, ROIC, Div Yield,
                          Margem Bruta, Margem Líquida)
  - Ratio Grid:           current vs 1Y/3Y averages grouped by category
  - Percentile Analysis:  full table showing all metrics

[v2.1 speed fix] The 6+ summary() calls + fetch_quartiles() calls are now
wrapped in `with engine_cache_scope():` so shared engines (earnings, pl,
shares, etc.) are queried ONCE across all metric calls instead of N times.
This was the root cause of the dashboard being slow — F7 only activates
inside compute_all_ratios(), which historical doesn't use. Now the cache
is activated explicitly.

This mode does NOT fetch new data -- it calls ``summary()`` once per
covered metric and reshapes the results into a multi-tab payload.

Registered as "dashboard" in skills.cvm.historical._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills._base import engine_cache_scope
from skills.cvm.historical._registry import register_mode
from skills.cvm.historical.modes.summary import summary
from skills.cvm.historical.report import (
    build_overview_kpis,
    build_overview_section,
    build_percentile_section,
    build_percentile_chart,
    build_trend_section,
    build_ratio_grid_section,
    fetch_quartiles,
)


# ── Metrics covered by the dashboard ────────────────────────────────────────
# (metric_name, KPI label, unit_kind, category) — unit_kind is "ratio" for
# price multiples (P/L, P/VPA, EV/EBITDA) and "pct" for profitability/yield
# ratios (ROE, ROIC, Div Yield, margins).
_METRIC_DEFS: list[tuple[str, str, str, str]] = [
    # Valuation
    ("lpa",            "P/L",              "ratio", "valuation"),
    ("vpa",            "P/VPA",            "ratio", "valuation"),
    ("ev_ebitda",      "EV/EBITDA",        "ratio", "valuation"),
    # Profitability
    ("roe",            "ROE",              "pct",   "profitability"),
    ("roic",           "ROIC",             "pct",   "profitability"),
    ("dpa",            "Div Yield",        "pct",   "profitability"),
    ("gross_margin",   "Marg. Bruta",      "pct",   "profitability"),
    ("net_margin",     "Marg. Líquida",    "pct",   "profitability"),
]

# Legacy 3-tuple for builders that still expect it
_METRIC_DEFS_3 = [(m, l, u) for m, l, u, _ in _METRIC_DEFS]


@register_mode(
    "dashboard",
    description=(
        "Multi-tab historical dashboard (thin composition of summary()). "
        "Tabs: Overview (8 KPI cards), Valuation (subtabs: percentile + "
        "trend), Profitability (subtabs: percentile + trend), Ratio Grid, "
        "Percentile Analysis (all metrics)."
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

    [v2.1] 5 tabs: Overview, Valuation (subtabs), Profitability (subtabs),
    Ratio Grid, Percentile Analysis.

    Args:
        company: Ticker. Required.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "tabs": [...],
        "kpis": [...]}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[historical] Starting dashboard for {company}...", flush=True)

    # ── Gather underlying data: call summary() once per covered metric ──
    # [v2.1 speed fix] Wrap ALL metric calls in engine_cache_scope() so
    # shared engines (earnings, pl, shares) are queried ONCE across all
    # 8 metrics instead of N times. This is the fix for the slow dashboard.
    summaries: dict[str, dict] = {}
    quartiles: dict[str, dict | None] = {}
    total = len(_METRIC_DEFS)

    print(f"[historical] Fetching {total} metric summaries (with F7 cache)...", flush=True)
    with engine_cache_scope() as cache:
        for i, (metric_name, label, _unit, _cat) in enumerate(_METRIC_DEFS, 1):
            print(f"[historical]   {i}/{total}: {label} ({metric_name})...", flush=True, end="")
            try:
                summaries[metric_name] = summary(company=company, metric=metric_name)
            except Exception as e:
                summaries[metric_name] = {"status": "error", "error": str(e)}
            print(" done.", flush=True)

        # ── Fetch quartiles within the SAME cache scope ──
        print(f"[historical] Fetching quartiles (5Y distribution)...", flush=True)
        for metric_name, _label, _unit, _cat in _METRIC_DEFS:
            s = summaries.get(metric_name) or {}
            if s.get("status") != "ok":
                quartiles[metric_name] = None
                continue
            quartiles[metric_name] = fetch_quartiles(company, metric_name, months=60)

        stats = cache.stats
        print(f"[historical] F7 cache: {stats['hits']} hits, {stats['misses']} misses, {stats['size']} entries.", flush=True)

    # ── Top-level KPI cards (one per metric) ──
    print(f"[historical] Building dashboard sections...", flush=True)
    kpis = build_overview_kpis(summaries, _METRIC_DEFS_3)

    # ── Split metrics by category for subtabs ──
    valuation_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "valuation"]
    profitability_metrics = [(m, l, u) for m, l, u, c in _METRIC_DEFS if c == "profitability"]

    # ── Tab 1: Overview -- Summary text section ──
    overview_sections = [build_overview_section(summaries, _METRIC_DEFS_3, company)]

    # ── Tab 2: Valuation -- subtabs (Percentile + Trend) ──
    val_summaries = {m: summaries.get(m, {}) for m, _, _ in valuation_metrics}
    val_quartiles = {m: quartiles.get(m) for m, _, _ in valuation_metrics}
    val_subtabs = []
    val_pct_table = build_percentile_section(val_summaries, val_quartiles, valuation_metrics)
    val_subtabs.append({"name": "Percentile", "sections": [val_pct_table]})
    val_chart = build_percentile_chart(val_summaries, val_quartiles, valuation_metrics)
    if val_chart:
        val_subtabs.append({"name": "Chart", "sections": [val_chart]})
    val_trend = build_trend_section(val_summaries, valuation_metrics)
    val_subtabs.append({"name": "Trend", "sections": [val_trend]})
    valuation_sections = [{"type": "subtabs", "tabs": val_subtabs}]

    # ── Tab 3: Profitability -- subtabs (Percentile + Trend) ──
    prof_summaries = {m: summaries.get(m, {}) for m, _, _ in profitability_metrics}
    prof_quartiles = {m: quartiles.get(m) for m, _, _ in profitability_metrics}
    prof_subtabs = []
    prof_pct_table = build_percentile_section(prof_summaries, prof_quartiles, profitability_metrics)
    prof_subtabs.append({"name": "Percentile", "sections": [prof_pct_table]})
    prof_chart = build_percentile_chart(prof_summaries, prof_quartiles, profitability_metrics)
    if prof_chart:
        prof_subtabs.append({"name": "Chart", "sections": [prof_chart]})
    prof_trend = build_trend_section(prof_summaries, profitability_metrics)
    prof_subtabs.append({"name": "Trend", "sections": [prof_trend]})
    profitability_sections = [{"type": "subtabs", "tabs": prof_subtabs}]

    # ── Tab 4: Ratio Grid -- current vs 1Y/3Y grouped by category ──
    grid_sections = [build_ratio_grid_section(summaries, _METRIC_DEFS_3)]

    # ── Tab 5: Percentile Analysis -- full table (all metrics) ──
    percentile_sections = [
        build_percentile_section(summaries, quartiles, _METRIC_DEFS_3),
    ]
    full_chart = build_percentile_chart(summaries, quartiles, _METRIC_DEFS_3)
    if full_chart:
        percentile_sections.append(full_chart)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    tabs = [
        {"name": "Overview",            "sections": overview_sections},
        {"name": "Valuation",           "sections": valuation_sections},
        {"name": "Profitability",       "sections": profitability_sections},
        {"name": "Ratio Grid",          "sections": grid_sections},
        {"name": "Percentile Analysis", "sections": percentile_sections},
    ]

    print(f"[historical] Done! {len(tabs)} tabs, {len(kpis)} KPIs.", flush=True)
    return {
        "status": "ok",
        "company": company,
        "tabs": tabs,
        "kpis": kpis,
    }
