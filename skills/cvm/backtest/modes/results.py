"""Mode: results -- analyze backtest results (extract key metrics).

Takes the dict returned by ``run()`` and produces a compact summary:
  - summary: 6 headline metrics (total return, CAGR, max drawdown, Sharpe,
    win rate, alpha)
  - trade_analysis: num trades, avg holding days, avg return per trade,
    best/worst trade

Registered as "results" in skills.cvm.backtest._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.backtest._registry import register_mode


@register_mode(
    "results",
    description=(
        "Analyze backtest results — extract key metrics for reporting. "
        "Takes the dict returned by run() and returns a summary."
    ),
    params={
        "backtest_result": "dict. The result from run() mode. Required.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="backtest", mode="results", params=\'{"backtest_result": <run result>}\')',
    ],
)
def results(backtest_result: dict = None) -> dict:
    """Analyze backtest results — extract key metrics for reporting.

    Args:
        backtest_result: The dict returned by run(). Required.

    Returns:
        Dict with performance summary + trade analysis.
    """
    if not backtest_result:
        return {"status": "error", "error": "backtest_result is required"}

    if backtest_result.get("status") != "ok":
        return backtest_result

    perf = backtest_result.get("performance", {})
    trades = backtest_result.get("trades", [])

    avg_holding = sum(t["holding_days"] for t in trades) / len(trades) if trades else 0
    avg_return = sum(t["return_pct"] for t in trades) / len(trades) if trades else 0
    best_trade = max(trades, key=lambda t: t["return_pct"]) if trades else None
    worst_trade = min(trades, key=lambda t: t["return_pct"]) if trades else None

    return {
        "status": "ok",
        "ticker": backtest_result.get("ticker"),
        "strategy": backtest_result.get("strategy"),
        "summary": {
            "total_return_pct": perf.get("total_return_pct"),
            "cagr_pct": perf.get("cagr_pct"),
            "max_drawdown_pct": perf.get("max_drawdown_pct"),
            "sharpe_ratio": perf.get("sharpe_ratio"),
            "win_rate_pct": perf.get("win_rate_pct"),
            "alpha_vs_buy_hold": perf.get("alpha_vs_buy_hold"),
        },
        "trade_analysis": {
            "num_trades": len(trades),
            "avg_holding_days": round(avg_holding, 1),
            "avg_return_per_trade_pct": round(avg_return, 2),
            "best_trade": {
                "entry_date": best_trade["entry_date"],
                "exit_date": best_trade["exit_date"],
                "return_pct": best_trade["return_pct"],
            } if best_trade else None,
            "worst_trade": {
                "entry_date": worst_trade["entry_date"],
                "exit_date": worst_trade["exit_date"],
                "return_pct": worst_trade["return_pct"],
            } if worst_trade else None,
        },
    }
