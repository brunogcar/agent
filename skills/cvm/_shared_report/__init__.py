"""skills/cvm/_shared_report — Shared report builders for CVM skills.

[v1.16.1] Extracted from skills/cvm/financials/report.py so all CVM skills
(financials, valuation, historical, governance, etc.) can reuse the same
company header, price chart, and tooltip system without copying code.

Usage:
    from skills.cvm._shared_report import build_company_header, build_price_chart, get_tooltip
"""
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm._shared_report.tooltips import get_tooltip, _METRIC_TOOLTIPS

__all__ = ["build_company_header", "build_price_chart", "get_tooltip", "_METRIC_TOOLTIPS"]
