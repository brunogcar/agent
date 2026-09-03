"""skills/cvm/financials/report/ -- Dashboard composition helpers package.

[v2.0] Split the original 3,981-line ``report.py`` into a package directory
following the same pattern used by ``skills/cvm/calculations/engines/<stmt>/``
subfolders (e.g., ``engines/dva/``, ``engines/dre/``). Each submodule hosts
builders for one dashboard tab/concern:

  - ``_helpers``    : shared utilities + constants (``_fmt``, ``_num_or_none``,
                      ``_pct_of``, ``_period_sort_key``, ``_format_period_label``,
                      label maps, color maps).
  - ``overview``    : Overview tab (KPIs, summary table, trend chart, radar,
                      heatmap).
  - ``indicadores`` : Indicadores tab (ratio_grid subtabs + per-group bar
                      charts).
  - ``crescimento`` : Crescimento tab (growth ratio_grid + 3M/1Y/5Y table +
                      per-metric bar charts).
  - ``statements``  : shared multi-period table + period_toggle wrapper used
                      by all 4 statement tabs.
  - ``balanco``     : Balanço tab (Completo / BPA / BPP subtabs + 6 stacked-
                      bar charts).
  - ``dre``         : DRE tab (multi-period table + margins chart + abs chart
                      + trend chart, all inside period_toggle).
  - ``dfc``         : DFC tab (multi-period table + stacked bar + FCO-vs-LL
                      + trend + quality section).
  - ``dva``         : DVA tab (multi-period table + doughnut + waterfall bar
                      + trend + dividend sustainability section).
  - ``analysis``    : analytical sections (red flags, DuPont, Altman Z, WACC).
  - ``periods``     : period-series builders (TTM, YoY, Anual, Trimestral).
  - ``error``       : error-section builder + utility helpers
                      (``_safe_engine_call``, ``annual_metric``, ``annual_ratio``,
                      ``_metrics_from_period``).

This ``__init__.py`` re-exports ALL public builders so existing imports
continue to work:

    from skills.cvm.financials.report import build_overview_kpis, ...

The previous ``report.py`` file (3,981 lines, 47 functions) has been
deleted; the ``report/`` package directory takes precedence (Python 3.3+
implicit namespace packages, but we ship an explicit ``__init__.py`` for
clarity + to set up the re-exports).
"""
from __future__ import annotations

# ── Re-exports from skills.cvm._shared_report (kept for backward compat) ────
# The original report.py re-exported these so dashboard.py could import them
# from this module. We preserve that behavior.
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart

# ── error.py — error utilities + small helpers ──────────────────────────────
from skills.cvm.financials.report.error import (
    annual_metric,
    annual_ratio,
    _metrics_from_period,  # noqa: F401 (re-exported for backward compat)
    _safe_engine_call,     # noqa: F401 (re-exported for backward compat)
    build_error_section,
)

# ── overview.py — Overview tab builders ─────────────────────────────────────
from skills.cvm.financials.report.overview import (
    build_overview_kpis,
    build_overview_sections,
    build_overview_trend_chart,
    build_financials_radar,
    build_financials_heatmap,
    build_quality_of_earnings_section,      # [v2.4] F16
    build_quality_of_earnings_chart,       # [v2.4] F16
    _fetch_year_end_prices,    # noqa: F401 (re-exported for backward compat)
    _attach_price_overlay,     # noqa: F401 (re-exported for backward compat)
)

# ── indicadores.py — Indicadores tab ────────────────────────────────────────
from skills.cvm.financials.report.indicadores import (
    build_indicadores_section,
    _group_metrics_by_prefix,         # noqa: F401
    _build_category_items,            # noqa: F401
    _build_group_bar_chart,           # noqa: F401
    _build_growth_ratio_grid_section, # noqa: F401
)

# ── crescimento.py — Crescimento tab ────────────────────────────────────────
from skills.cvm.financials.report.crescimento import (
    build_crescimento_sections,
    _period_date,         # noqa: F401
    _build_metric_periods, # noqa: F401
)

# ── statements.py — shared statement table builders ────────────────────────
from skills.cvm.financials.report.statements import (
    build_multi_period_table,
    _statement_table_section,        # noqa: F401
    _merge_bpa_bpp_periods,          # noqa: F401
    _build_period_toggle_sections,   # noqa: F401
)

# ── balanco.py — Balanço tab ────────────────────────────────────────────────
from skills.cvm.financials.report.balanco import (
    build_balanco_section,
    build_balanco_chart,
    build_balanco_decomp_charts,
)

# ── dre.py — DRE tab ────────────────────────────────────────────────────────
from skills.cvm.financials.report.dre import (
    build_dre_sections,
    build_statement_trend_chart,
    _build_dre_margins_chart,  # noqa: F401
    _build_dre_abs_chart,      # noqa: F401
)

# ── dfc.py — DFC tab ────────────────────────────────────────────────────────
from skills.cvm.financials.report.dfc import (
    build_dfc_sections,
    build_dfc_trend_chart,
    build_dfc_quality_section,
    _build_dfc_stacked_chart,    # noqa: F401
    _build_dfc_fco_vs_ll_chart,  # noqa: F401
)

# ── dva.py — DVA tab ────────────────────────────────────────────────────────
from skills.cvm.financials.report.dva import (
    build_dva_sections,
    build_dva_trend_chart,
    build_dividend_sustainability_section,
    _build_dva_generation_chart,  # noqa: F401
)

# ── analysis.py — analytical sections ───────────────────────────────────────
from skills.cvm.financials.report.analysis import (
    build_red_flags_section,
    build_dupont_section,
    build_altman_z_section,
    build_wacc_section,
)

# ── periods.py — period series (TTM/YoY/Anual/Trimestral) ──────────────────
from skills.cvm.financials.report.periods import (
    build_ttm_chart,
    build_ttm_table,
    build_yoy_chart,
    build_yoy_table,
    build_period_table,
    build_period_chart,
    build_period_margins_chart,  # [v11] new margins bar chart for Períodos tabs
    build_ttm_margins_chart,     # [v11] new margins bar chart for Anualizado tab
)

# ── comprehensive.py — comprehensive period table [v14] ───────────────────
from skills.cvm.financials.report.comprehensive import (
    build_comprehensive_period_table,
    build_indicator_charts,
)


__all__ = [
    # _shared_report re-exports
    "build_company_header",
    "build_price_chart",
    # error.py
    "annual_metric",
    "annual_ratio",
    "build_error_section",
    # overview.py
    "build_overview_kpis",
    "build_overview_sections",
    "build_overview_trend_chart",
    "build_financials_radar",
    "build_financials_heatmap",
    "build_quality_of_earnings_section",   # [v2.4] F16
    "build_quality_of_earnings_chart",    # [v2.4] F16
    # indicadores.py
    "build_indicadores_section",
    # crescimento.py
    "build_crescimento_sections",
    # statements.py
    "build_multi_period_table",
    # balanco.py
    "build_balanco_section",
    "build_balanco_chart",
    "build_balanco_decomp_charts",
    # dre.py
    "build_dre_sections",
    "build_statement_trend_chart",
    # dfc.py
    "build_dfc_sections",
    "build_dfc_trend_chart",
    "build_dfc_quality_section",
    # dva.py
    "build_dva_sections",
    "build_dva_trend_chart",
    "build_dividend_sustainability_section",
    # analysis.py
    "build_red_flags_section",
    "build_dupont_section",
    "build_altman_z_section",
    "build_wacc_section",
    # periods.py
    "build_ttm_chart",
    "build_ttm_table",
    "build_yoy_chart",
    "build_yoy_table",
    "build_period_table",
    "build_period_chart",
    "build_period_margins_chart",
    "build_ttm_margins_chart",
    # comprehensive.py
    "build_comprehensive_period_table",
    "build_indicator_charts",
]
