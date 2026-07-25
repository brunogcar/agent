"""adapters/comparison.py — Flatten comparison skill JSON → table data.

Adapters:
  comparison_side_by_side — 3 sections (valuation, financials, dividends),
                            tickers as rows, metrics as columns.
  comparison_summary      — single quick-compare table (10 KPIs).

The comparison skill already returns sections in the generic table shape
(columns/rows/formats), so these adapters are thin: they pass through the
sections, extract KPIs from the summary mode, and add a KPI strip showing
the tickers compared.
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table


def _kpis_from_summary(section: dict) -> list[dict]:
    """Build a small KPI strip: one card per ticker showing its P/L."""
    from tools.report_ops.formats import apply_fmt
    kpis = []
    rows = section.get("rows") or []
    columns = section.get("columns") or []
    # Find the P/L column index if present
    pl_idx = columns.index("P/L") if "P/L" in columns else -1
    for row in rows:
        ticker = row[0] if row else "?"
        pl_val = row[pl_idx] if pl_idx > 0 and pl_idx < len(row) else None
        kpis.append({
            "label": ticker,
            "value": apply_fmt(pl_val, "num") if pl_val is not None else "—",
        })
    return kpis


@register_adapter("comparison_side_by_side")
def side_by_side(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Comparison")
    sections = result.get("sections") or {}
    if not sections:
        return _error_table(result, title="Comparison")

    out_sections = []
    # sections is a dict {valuation: {...}, financials: {...}, dividends: {...}}
    for _name, sec in sections.items():
        if isinstance(sec, dict) and sec.get("columns"):
            out_sections.append(sec)

    if not out_sections:
        return _error_table(result, title="Comparison")

    return {
        "company": " vs ".join(result.get("tickers") or []),
        "sections": out_sections,
        "kpis": [],
        "sources": [],
    }


@register_adapter("comparison_summary")
def summary(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Comparison Summary")
    sections = result.get("sections") or []
    if not sections or not isinstance(sections, list):
        return _error_table(result, title="Comparison Summary")

    section = sections[0]
    if not isinstance(section, dict) or not section.get("columns"):
        return _error_table(result, title="Comparison Summary")

    return {
        "company": " vs ".join(result.get("tickers") or []),
        "sections": [section],
        "kpis": _kpis_from_summary(section),
        "sources": [],
    }
