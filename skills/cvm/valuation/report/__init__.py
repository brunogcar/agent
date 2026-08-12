"""skills/cvm/valuation/report/__init__.py — Valuation report package.

[v2.0] Split from the monolithic report.py (1854 lines) into a package
with one file per dashboard tab/concern. This file re-exports all public
builders so existing imports (`from skills.cvm.valuation.report import X`)
continue to work without changes.

File map:
  _helpers.py        — _safe_get, _fmt, _safe_div, _derive_*, constants
  overview.py        — build_overview_kpis, build_overview_sections,
                       build_valuation_radar, build_valuation_heatmap
  multiples.py       — build_multiples_sections, build_per_share_sections
  profitability.py   — build_profitability_section, build_margin_trend_chart
  liquidity.py       — build_liquidity_leverage_sections
  efficiency.py      — build_efficiency_growth_sections
  intrinsic.py       — _dcf_at_growth, build_dcf_sensitivity_section
  history_charts.py  — build_pl_lpa_pvp_vpa_history_chart, build_roe_trend_chart
"""
from __future__ import annotations

# Re-export all public builders
from skills.cvm.valuation.report._helpers import (
    _safe_get, _fmt, _safe_div,
    _derive_multiples, _derive_per_share, _derive_detailed_leverage,
)
from skills.cvm.valuation.report.overview import (
    build_overview_kpis,
    build_overview_sections,
    build_valuation_radar,
    build_valuation_heatmap,
)
from skills.cvm.valuation.report.multiples import (
    build_multiples_sections,
    build_per_share_sections,
)
from skills.cvm.valuation.report.profitability import (
    build_profitability_section,
    build_margin_trend_chart,
)
from skills.cvm.valuation.report.liquidity import (
    build_liquidity_leverage_sections,
)
from skills.cvm.valuation.report.efficiency import (
    build_efficiency_growth_sections,
)
from skills.cvm.valuation.report.intrinsic import (
    build_dcf_sensitivity_section,
)
from skills.cvm.valuation.report.history_charts import (
    build_pl_lpa_pvp_vpa_history_chart,
    build_roe_trend_chart,
)

__all__ = [
    "build_overview_kpis",
    "build_overview_sections",
    "build_valuation_radar",
    "build_valuation_heatmap",
    "build_multiples_sections",
    "build_per_share_sections",
    "build_profitability_section",
    "build_margin_trend_chart",
    "build_liquidity_leverage_sections",
    "build_efficiency_growth_sections",
    "build_dcf_sensitivity_section",
    "build_pl_lpa_pvp_vpa_history_chart",
    "build_roe_trend_chart",
]
