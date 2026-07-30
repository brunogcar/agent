"""skills/cvm/comparison/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the side_by_side + growth comparison results into a multi-tab
dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _find_leader(section: dict, col_label: str, direction: str) -> tuple[str | None, float | None]:
    """Find the ticker with the min/max value for ``col_label``.

    ``direction`` is "min" or "max". Returns ``(ticker, value)`` where value
    is the raw number (NOT pre-formatted). Returns ``(None, None)`` when no
    row has a numeric value for the column.
    """
    columns = section.get("columns") or []
    rows = section.get("rows") or []
    if col_label not in columns:
        return None, None
    idx = columns.index(col_label)
    best_ticker, best_value = None, None
    for row in rows:
        if len(row) <= idx:
            continue
        value = row[idx]
        ticker = row[0] if row else ""
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if best_value is None:
            best_ticker, best_value = ticker, v
        elif direction == "min" and v < best_value:
            best_ticker, best_value = ticker, v
        elif direction == "max" and v > best_value:
            best_ticker, best_value = ticker, v
    return best_ticker, best_value


def _kpi(label: str, ticker: str | None, value: float | None,
         spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted as ``"<ticker> (<formatted>)"`` so the adapter
    can pass it through verbatim. When ticker/value is None, falls back to "—".
    """
    if ticker is None or value is None:
        return {"label": label, "value": "—", "unit": unit}
    formatted = _fmt(value, spec)
    return {"label": label, "value": f"{ticker} ({formatted})", "unit": unit}


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(side_by_side_result: dict) -> list[dict]:
    """Build the 4 KPI cards for the dashboard top-level kpis list.

    Cards (from the compared tickers):
      - Cheapest P/L         — lowest non-None P/L
      - Best ROE             — highest non-None ROE (financials section)
      - Best Div Yield       — highest non-None Div Yield (valuation section)
      - Cheapest EV/EBITDA   — lowest non-None EV/EBITDA
    """
    sections = side_by_side_result.get("sections") or {}
    valuation_section = sections.get("valuation") or {}
    financials_section = sections.get("financials") or {}

    pl_ticker, pl_value = _find_leader(valuation_section, "P/L", "min")
    roe_ticker, roe_value = _find_leader(financials_section, "ROE", "max")
    dy_ticker, dy_value = _find_leader(valuation_section, "Div Yield", "max")
    evebitda_ticker, evebitda_value = _find_leader(valuation_section, "EV/EBITDA", "min")

    return [
        _kpi("Cheapest P/L",       pl_ticker,       pl_value,       "num", "num"),
        _kpi("Best ROE",           roe_ticker,      roe_value,      "pct", "pct"),
        _kpi("Best Div Yield",     dy_ticker,       dy_value,       "pct", "pct"),
        _kpi("Cheapest EV/EBITDA", evebitda_ticker, evebitda_value, "num", "num"),
    ]


# ── Overview tab sections ────────────────────────────────────────────────────

def build_tickers_section(side_by_side_result: dict) -> dict:
    """Build the Compared Tickers table for the Overview tab.

    Two columns: Ticker, Setor (sector from CAD via _fetch_sectors).
    """
    tickers = side_by_side_result.get("tickers") or []
    sectors = side_by_side_result.get("sectors") or {}
    rows = [[t, sectors.get(t, "")] for t in tickers]
    return {
        "title": "Compared Tickers",
        "type": "table",
        "columns": ["Ticker", "Setor"],
        "rows": rows,
        "formats": {"Ticker": "text", "Setor": "text"},
    }


def build_errors_section(side_by_side_result: dict) -> dict | None:
    """If the comparison captured any per-ticker errors, surface them as a
    table section. Returns None when there are no errors.
    """
    errors = side_by_side_result.get("errors") or []
    if not errors:
        return None
    rows = [[i + 1, msg] for i, msg in enumerate(errors)]
    return {
        "title": "Per-Ticker Errors (best-effort)",
        "type": "table",
        "columns": ["#", "Error"],
        "rows": rows,
        "formats": {"#": "int", "Error": "text"},
    }


# ── Passthrough section builders ─────────────────────────────────────────────
# The side_by_side mode already builds each section in the generic table shape
# (columns/rows/formats). These helpers just re-tag the section with
# type="table" and pull it out of the sections dict for the dashboard tabs.

def _as_table_section(section: dict) -> dict:
    """Ensure a section has type='table' (dashboard sections are typed)."""
    out = dict(section)
    out.setdefault("type", "table")
    return out


def build_valuation_section(side_by_side_result: dict) -> dict:
    """Build the Valuation tab section from side_by_side()['sections']['valuation']."""
    sections = side_by_side_result.get("sections") or {}
    return _as_table_section(sections.get("valuation") or {
        "title": "Valuation Ratios", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    })


def build_financials_section(side_by_side_result: dict) -> dict:
    """Build the Financials tab section from side_by_side()['sections']['financials']."""
    sections = side_by_side_result.get("sections") or {}
    return _as_table_section(sections.get("financials") or {
        "title": "Financial Metrics (latest annual)", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    })


def build_dividends_section(side_by_side_result: dict) -> dict:
    """Build the Dividends tab section from side_by_side()['sections']['dividends']."""
    sections = side_by_side_result.get("sections") or {}
    return _as_table_section(sections.get("dividends") or {
        "title": "Dividend Metrics", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    })


def build_growth_section(growth_result: dict) -> dict:
    """Build the Growth tab section from growth()['sections'][0].

    The growth mode returns sections as a list (single-element); this helper
    extracts that section and re-tags it with type='table'.
    """
    sections = growth_result.get("sections") or []
    if not sections:
        return {
            "title": "Growth Metrics (QoQ + YoY + TTM)", "type": "table",
            "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
        }
    return _as_table_section(sections[0])
