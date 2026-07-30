"""skills/cvm/backtest/report.py -- Dashboard composition helpers.

Produces sections + KPI cards in the same shape used by the dashboard
template (mirrors skills/cvm/financials/report.py + skills/cvm/valuation/
report.py):
  - KPI card:  {"label": str, "value": str, "unit": str}
  - Text section:  {"title": str, "type": "text", "text": str}
  - Chart section: {"title": str, "type": "chart", "chart_data": <Chart.js config>}
  - Table section: {"title": str, "type": "table", "columns": [...],
                     "rows": [...], "formats": {...}}

Used by skills.cvm.backtest.modes.dashboard to assemble the multi-tab
dashboard payload. Reusable by other modes / tests.

The sections produced here are the canonical dashboard shape, so the
report tool's `backtest_dashboard` adapter can simply pass them through.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


# Equity curve line color (matches the brand teal of the report theme).
_EQUITY_COLOR = "#0d9488"


def _fmt(value: Any, spec: str) -> str:
    """Format a value via the report_ops formats registry, defensive."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


# ── Overview KPI cards (top-level) ───────────────────────────────────────────

def build_overview_kpis(perf: dict) -> list[dict]:
    """Build 6 KPI cards from the performance metrics dict.

    Each card is shaped as ``{"label", "value", "unit"}`` so the
    financials_dashboard-style adapter (and any other consumer) can map
    the unit to a format spec.
    """
    return [
        {"label": "CAGR",          "value": _fmt(perf.get("cagr_pct"), "pct_raw"),
         "unit": "pct"},
        {"label": "Total Return",  "value": _fmt(perf.get("total_return_pct"), "pct_raw"),
         "unit": "pct"},
        {"label": "Max Drawdown",  "value": _fmt(perf.get("max_drawdown_pct"), "pct_raw"),
         "unit": "pct"},
        {"label": "Sharpe",        "value": _fmt(perf.get("sharpe_ratio"), "num"),
         "unit": "num"},
        {"label": "Win Rate",      "value": _fmt(perf.get("win_rate_pct"), "pct_raw"),
         "unit": "pct"},
        {"label": "Alpha",         "value": _fmt(perf.get("alpha_vs_buy_hold"), "pct_raw"),
         "unit": "pct"},
    ]


# ── Overview tab sections ────────────────────────────────────────────────────

def build_strategy_section(result: dict) -> dict:
    """Build the strategy description as a text section.

    Uses plain text (no HTML) so the autoescaped template renders it verbatim.
    """
    ticker = result.get("ticker", "")
    strategy = result.get("strategy", "")
    description = result.get("strategy_description", "")
    start_date = result.get("start_date", "")
    end_date = result.get("end_date", "")
    initial_capital = result.get("initial_capital", 0)
    final_equity = result.get("final_equity", 0)

    lines = [
        f"Ticker: {ticker}    Strategy: {strategy}",
        f"Description: {description}",
        f"Period: {start_date} -> {end_date}",
        f"Capital: R$ {initial_capital:,.2f} -> R$ {final_equity:,.2f}",
    ]
    return {
        "title": "Strategy",
        "type": "text",
        "text": "\n".join(lines),
    }


def build_equity_curve_section(equity_curve: list) -> dict:
    """Build a Chart.js line chart config section for the equity curve.

    The dashboard template passes ``chart_data`` directly to ``new Chart(ctx,
    chart_data)``, so this must be a full Chart.js config (not the {x, y}
    shape used by the standalone chart action).
    """
    # Equity curve is oldest-first by construction in backtest.run()
    labels = [pt.get("date", "") for pt in equity_curve]
    values = [pt.get("equity") for pt in equity_curve]
    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": "Equity (R$)",
                "data": values,
                "borderColor": _EQUITY_COLOR,
                "backgroundColor": "rgba(13, 148, 136, 0.15)",
                "borderWidth": 2,
                "tension": 0.3,
                "fill": True,
            }],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True, "position": "bottom"},
                "title": {"display": True, "text": "Equity Curve"},
            },
            "scales": {
                "x": {"grid": {"display": False}},
                "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
            },
        },
    }
    return {
        "title": "Equity Curve",
        "type": "chart",
        "chart_data": chart_data,
    }


# ── Trades tab ───────────────────────────────────────────────────────────────

def build_trades_section(trades: list) -> dict:
    """Build the trade log table section.

    Columns match the trade dict emitted by backtest.run() exactly.
    """
    columns = [
        "Entry Date", "Entry Price", "Exit Date", "Exit Price",
        "Shares", "PnL (R$)", "Return %", "Holding Days", "Exit Reason",
    ]
    rows = []
    for t in trades:
        rows.append([
            t.get("entry_date", ""),
            t.get("entry_price"),
            t.get("exit_date", ""),
            t.get("exit_price"),
            t.get("shares"),
            t.get("pnl"),
            t.get("return_pct"),
            t.get("holding_days"),
            t.get("exit_reason", ""),
        ])
    return {
        "title": "Trade Log",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": {
            "Entry Price": "brl_full",
            "Exit Price": "brl_full",
            "PnL (R$)": "brl_full",
            "Return %": "pct_raw",
            "Shares": "int",
            "Holding Days": "int",
            "Entry Date": "text",
            "Exit Date": "text",
            "Exit Reason": "text",
        },
        "note": f"{len(rows)} trade(s) executed.",
    }


# ── Performance tab ──────────────────────────────────────────────────────────

def build_performance_section(perf: dict) -> dict:
    """Build the performance summary table section (metric, value).

    Two-column table with pre-formatted values so the dashboard template
    renders them verbatim.
    """
    columns = ["Metric", "Value"]
    rows = [
        ["Total Return",          _fmt(perf.get("total_return_pct"),   "pct_raw")],
        ["CAGR",                  _fmt(perf.get("cagr_pct"),           "pct_raw")],
        ["Max Drawdown",          _fmt(perf.get("max_drawdown_pct"),   "pct_raw")],
        ["Sharpe Ratio",          _fmt(perf.get("sharpe_ratio"),       "num")],
        ["Win Rate",              _fmt(perf.get("win_rate_pct"),       "pct_raw")],
        ["Number of Trades",      _fmt(perf.get("num_trades"),         "int")],
        ["Buy & Hold Return",     _fmt(perf.get("buy_hold_return_pct"),"pct_raw")],
        ["Alpha vs Buy & Hold",   _fmt(perf.get("alpha_vs_buy_hold"),  "pct_raw")],
    ]
    return {
        "title": "Performance Summary",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }
