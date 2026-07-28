"""adapters/backtest.py — Flatten backtest run() result → report payload.

Adapter:
  backtest — multi-section report with KPIs, strategy description, equity curve
             chart, trade log table, and performance summary table.

Accepts a backtest run() result dict (see skills/cvm/backtest/backtest.py):
    {"status":"ok", "ticker":"PETR4", "strategy":"value_pe",
     "strategy_description":"...", "start_date":..., "end_date":...,
     "initial_capital":..., "final_equity":...,
     "performance": {"total_return_pct","cagr_pct","max_drawdown_pct",
                     "sharpe_ratio","win_rate_pct","num_trades",
                     "buy_hold_return_pct","alpha_vs_buy_hold"},
     "trades":[{entry_date,entry_price,exit_date,exit_price,shares,pnl,
                return_pct,holding_days,exit_reason}, ...],
     "equity_curve":[{date,equity}, ...]}

Returns the generic report shape:
    {"company": <ticker>, "sections": [...], "kpis": [...], "sources": []}

Sections (in order):
  1. Strategy       — text section (ticker, strategy name, description, period)
  2. Equity Curve   — Chart.js line chart config (equity over time)
  3. Trade Log      — table (entry/exit dates+prices, shares, pnl, return%,
                      holding days, exit reason)
  4. Performance    — table (metric, value) — CAGR, returns, drawdown, Sharpe,
                      win rate, alpha, # trades, buy & hold return

Usage:
  report(action="report", title="PETR4 value_pe Backtest",
         data=<backtest run() result>,
         config={"adapter":"backtest"})

  report(action="dashboard", title="PETR4 Backtest Dashboard",
         data=<backtest run() result>,
         config={"adapter":"backtest"})
"""
from __future__ import annotations

from tools.report_ops.adapters import register_adapter, _ok, _error_table


# Equity curve line color (matches the brand teal of the report theme).
_EQUITY_COLOR = "#0d9488"


def _kpis(perf: dict) -> list[dict]:
    """Build KPI cards from the performance metrics dict."""
    return [
        {"label": "CAGR", "value": f"{perf.get('cagr_pct', 0):.2f}%"},
        {"label": "Total Return", "value": f"{perf.get('total_return_pct', 0):.2f}%"},
        {"label": "Max Drawdown", "value": f"{perf.get('max_drawdown_pct', 0):.2f}%"},
        {"label": "Sharpe", "value": f"{perf.get('sharpe_ratio', 0):.2f}"},
        {"label": "Win Rate", "value": f"{perf.get('win_rate_pct', 0):.1f}%"},
        {"label": "Alpha", "value": f"{perf.get('alpha_vs_buy_hold', 0):.2f}%"},
    ]


def _strategy_section(result: dict) -> dict:
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
        f"Period: {start_date} → {end_date}",
        f"Capital: R$ {initial_capital:,.2f} → R$ {final_equity:,.2f}",
    ]
    return {
        "title": "Strategy",
        "type": "text",
        "text": "\n".join(lines),
    }


def _equity_chart_section(equity_curve: list) -> dict:
    """Build a Chart.js line chart config section for the equity curve.

    The report/dashboard templates pass `chart_data` directly to `new Chart(ctx,
    chart_data)`, so this must be a full Chart.js config (not the {x, y} shape
    used by the standalone chart action).
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


def _trade_log_section(trades: list) -> dict:
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


def _performance_summary_section(perf: dict) -> dict:
    """Build the performance summary table section (metric, value)."""
    columns = ["Metric", "Value"]
    rows = [
        ["Total Return", f"{perf.get('total_return_pct', 0):.2f}%"],
        ["CAGR", f"{perf.get('cagr_pct', 0):.2f}%"],
        ["Max Drawdown", f"{perf.get('max_drawdown_pct', 0):.2f}%"],
        ["Sharpe Ratio", f"{perf.get('sharpe_ratio', 0):.2f}"],
        ["Win Rate", f"{perf.get('win_rate_pct', 0):.1f}%"],
        ["Number of Trades", str(perf.get("num_trades", 0))],
        ["Buy & Hold Return", f"{perf.get('buy_hold_return_pct', 0):.2f}%"],
        ["Alpha vs Buy & Hold", f"{perf.get('alpha_vs_buy_hold', 0):.2f}%"],
    ]
    return {
        "title": "Performance Summary",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }


@register_adapter("backtest")
def backtest_adapter(result: dict) -> dict:
    """Flatten backtest.run() result into a multi-section report payload."""
    if not _ok(result):
        return _error_table(result, title="Backtest")

    perf = result.get("performance") or {}
    trades = result.get("trades") or []
    equity_curve = result.get("equity_curve") or []

    sections = [
        _strategy_section(result),
        _equity_chart_section(equity_curve),
        _trade_log_section(trades),
        _performance_summary_section(perf),
    ]

    return {
        "company": result.get("ticker", ""),
        "sections": sections,
        "kpis": _kpis(perf),
        "sources": [],
    }
