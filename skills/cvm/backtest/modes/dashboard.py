"""Mode: dashboard -- multi-tab backtest dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview: KPI cards (CAGR, Total Return, Max Drawdown, Sharpe, Win Rate,
    Alpha) + strategy description + equity curve chart
  - Trades: trade log table (entry/exit dates+prices, shares, PnL, return%,
    holding days, exit reason)
  - Performance: performance summary table (all metrics)

This mode does NOT fetch new data -- it calls ``run()`` (with the same
``ticker`` / ``strategy`` / ``start_date`` / ``end_date`` / ``initial_capital``
parameters) and reshapes its output into a multi-tab payload. If ``run()``
fails (e.g. no price data, unknown strategy), the dashboard propagates the
error dict instead of crashing.

The section-building helpers live in skills.cvm.backtest.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.backtest._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.backtest._registry import register_mode
from skills.cvm.backtest.modes.run import run
from skills.cvm.backtest.report import (
    build_overview_kpis,
    build_strategy_section,
    build_equity_curve_section,
    build_trades_section,
    build_performance_section,
    build_drawdown_section,
)


@register_mode(
    "dashboard",
    description=(
        "Multi-tab backtest dashboard (thin composition of run()). Tabs: "
        "Overview (6 KPI cards + strategy + equity curve), Trades (trade "
        "log), Performance (summary table). Optimized for the report "
        "tool's dashboard action."
    ),
    params={
        "ticker":          "str. B3 ticker (e.g., PETR4). Required.",
        "strategy":        "str. Strategy name. Default: value_pe.",
        "start_date":      "str. Backtest start date (YYYY-MM-DD). Default: 3 years ago.",
        "end_date":        "str. Backtest end date (YYYY-MM-DD). Default: today.",
        "initial_capital": "float. Starting capital in BRL. Default: 10000.",
        "max_positions":   "int. Max simultaneous positions. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="backtest", mode="dashboard", params=\'{"ticker":"PETR4","strategy":"value_pe"}\')',
    ],
)
def dashboard(
    ticker: str = "",
    strategy: str = "value_pe",
    start_date: str = "",
    end_date: str = "",
    initial_capital: float = 10000.0,
    max_positions: int = 1,
) -> dict:
    """Multi-tab backtest dashboard (thin composition of run()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview: KPI cards (CAGR, Total Return, Max Drawdown, Sharpe, Win
        Rate, Alpha) + strategy description + equity curve chart
      - Trades: trade log table (entry/exit dates+prices, shares, PnL,
        return%, holding days, exit reason)
      - Performance: performance summary table (all 8 metrics)

    This mode does NOT fetch new data -- it calls ``run()`` (forwarding the
    same kwargs) and reshapes its output into a multi-tab payload. If
    ``run()`` fails (e.g. no price data, unknown strategy), the dashboard
    propagates the error dict instead of crashing.

    Args:
        ticker: B3 ticker (e.g., "PETR4"). Required.
        strategy: Strategy name from BUILTIN_STRATEGIES. Default: "value_pe".
        start_date: Backtest start date (YYYY-MM-DD). Default: 3 years ago.
        end_date: Backtest end date (YYYY-MM-DD). Default: today.
        initial_capital: Starting capital in BRL. Default: 10000.
        max_positions: Max simultaneous positions. Currently only 1 is
            supported. Default: 1.

    Returns:
        Dict shaped as ``{"status": "ok", "ticker": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        The Overview tab additionally carries a ``kpis`` list. On empty
        ticker or run() failure, returns the run() error dict verbatim.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    print(f"[backtest] Starting backtest: {ticker} / {strategy}...", flush=True)

    # ── Gather underlying data (run() wrapped defensively) ─────────────────
    print(f"[backtest] Running strategy backtest...", flush=True)
    try:
        run_result = run(
            ticker=ticker,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            max_positions=max_positions,
        )
    except Exception as e:
        return {"status": "error",
                "sub_domain": "backtest", "mode": "dashboard",
                "error": str(e)}

    # Propagate run() failures (ticker missing, no price data, unknown
    # strategy, etc.) as-is rather than rendering empty tabs.
    if run_result.get("status") != "ok":
        return run_result

    perf = run_result.get("performance") or {}
    trades = run_result.get("trades") or []
    equity_curve = run_result.get("equity_curve") or []

    print(f"[backtest] Backtest complete: {len(trades)} trades, "
          f"{perf.get('num_trades', 0)} total, "
          f"return={perf.get('total_return_pct', 0):.2f}%", flush=True)

    # ── Top-level KPI cards (Overview tab's KPIs) ──────────────────────────
    print(f"[backtest] Building dashboard sections...", flush=True)
    kpis = build_overview_kpis(perf)

    # ── Tab 1: Overview -- strategy description + equity curve chart ───────
    overview_sections = [
        build_strategy_section(run_result),
        build_equity_curve_section(equity_curve),
    ]

    # ── Tab 2: Trades -- trade log table ───────────────────────────────────
    trades_sections = [build_trades_section(trades)]

    # ── Tab 3: Performance -- performance summary table + drawdown chart ──
    performance_sections = [build_performance_section(perf)]
    drawdown = build_drawdown_section(equity_curve)
    if drawdown:
        performance_sections.append(drawdown)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) -- the dashboard template
    # renders them above all tabs via the kpi-grid div.
    tabs = [
        {"name": "Overview",    "sections": overview_sections},
        {"name": "Trades",      "sections": trades_sections},
        {"name": "Performance", "sections": performance_sections},
    ]
    print(f"[backtest] Done! {len(tabs)} tabs, {len(kpis)} KPIs, {len(trades)} trades.", flush=True)
    return {
        "status": "ok",
        "ticker": run_result.get("ticker", ""),
        "strategy": run_result.get("strategy", ""),
        "tabs": tabs,
        "kpis": kpis,
    }
