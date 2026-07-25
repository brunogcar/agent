"""Table action handler — renders tabular statements (financials, ratios, lists).

Lazy-imports the heavy table builder to keep MCP startup fast.

Supports an optional ``config["adapter"]`` that flattens a raw skill JSON into
the table data shape (see tools/report_ops/transforms/).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops._registry import register_action


@register_action(
    "report",
    "table",
    help_text="""Render one or more tables with per-column number formatting (BRL, %, ...).
Required: title, data (table-shape dict OR a skill result with config['adapter'])
data shape: {"sections":[{"title","columns","rows","formats","note"}], "kpis":[...], "sources":[...]}
Optional: config (adapter, theme, accent, subtitle)
Adapters: financials_quarterly | financials_annual | financials_summary |
          valuation_ratios | valuation_summary |
          shareholders_shareholders | shareholders_free_float |
          shareholders_equity_structure | shareholders_summary |
          dividends_history | dividends_annual | dividends_summary
Returns: {type, title, html_path, sections, total_rows, adapter}""",
    examples=[
        'report(action="table", title="PETR4 Financials", data={"sections":[{"title":"Q","columns":["P","Rev"],"rows":[["1T26",1000]]}]})',
        'report(action="table", title="PETR4 Financials", data=<financials skill JSON>, config={"adapter":"financials_quarterly"})',
        'report(action="table", title="Valuation", data=<valuation skill JSON>, config={"adapter":"valuation_ratios"})',
    ],
)
def run_table(
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    **kwargs,
) -> dict:
    """Build a tabular report. Delegates to the table builder."""
    from tools.report_ops import table
    return table.build(
        trace_id=trace_id,
        title=title,
        data=data,
        config=config or {},
    )
