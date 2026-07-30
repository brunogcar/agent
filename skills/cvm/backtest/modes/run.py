"""Mode: run -- run a backtest strategy on a single ticker over a date range.

The main backtest engine. Pre-computes signal values ONCE before the loop
(v1.1 step-function optimization), then iterates through price bars:
  - On each bar, check exit conditions first (if holding a position).
  - Then check entry conditions (if not holding a position).
  - Track equity curve + max drawdown + daily returns (for Sharpe).

Returns a result dict with: trades, performance metrics (CAGR, total return,
max drawdown, Sharpe ratio, win rate, buy & hold return, alpha), and equity
curve.

Registered as "run" in skills.cvm.backtest._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from skills.cvm.backtest._registry import register_mode
from skills.cvm.backtest.helpers import (
    BUILTIN_STRATEGIES,
    _precompute_signals,
)


@register_mode(
    "run",
    description=(
        "Run a backtest strategy on a single ticker. Returns trades, "
        "performance metrics (CAGR, total return, max drawdown, Sharpe "
        "ratio, win rate), and equity curve."
    ),
    params={
        "ticker":          "str. B3 ticker (e.g., PETR4). Required.",
        "strategy":        "str. Strategy name (value_pe, value_pvpa, quality_roe, "
                           "quality_roic, income_dy, composite). Default: value_pe.",
        "start_date":      "str. Backtest start date (YYYY-MM-DD). Default: 3 years ago.",
        "end_date":        "str. Backtest end date (YYYY-MM-DD). Default: today.",
        "initial_capital": "float. Starting capital in BRL. Default: 10000.",
        "max_positions":   "int. Max simultaneous positions. Default: 1.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="cvm", sub_domain="backtest", mode="run", params=\'{"ticker":"PETR4","strategy":"value_pe"}\')',
        'skill(domain="cvm", sub_domain="backtest", mode="run", params=\'{"ticker":"VALE3","strategy":"composite","start_date":"2022-01-01"}\')',
    ],
)
def run(
    ticker: str = "",
    strategy: str = "value_pe",
    start_date: str = "",
    end_date: str = "",
    initial_capital: float = 10000.0,
    max_positions: int = 1,
) -> dict:
    """Run a backtest strategy on a single ticker.

    Args:
        ticker: B3 ticker (e.g., "PETR4"). Required.
        strategy: Strategy name from BUILTIN_STRATEGIES. Default: "value_pe".
        start_date: Backtest start date (YYYY-MM-DD). Default: 3 years ago.
        end_date: Backtest end date (YYYY-MM-DD). Default: today.
        initial_capital: Starting capital in BRL. Default: 10000.
        max_positions: Max simultaneous positions. Currently only 1 is
            supported (single-position mode). Values > 1 raise ValueError
            so callers don't silently get single-position behaviour when
            they expect multi-position. Default: 1.

    Returns:
        Dict with trades, performance metrics (CAGR, total return, max drawdown,
        Sharpe ratio), and equity curve.
    """
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    ticker = ticker.strip().upper()
    strategy = strategy.strip().lower()

    if max_positions != 1:
        raise ValueError(
            f"max_positions={max_positions} is not supported. This engine "
            f"currently runs in single-position mode only (max_positions=1). "
            f"Multi-position backtesting is not implemented."
        )

    if strategy not in BUILTIN_STRATEGIES:
        return {"status": "error",
                "error": f"Unknown strategy '{strategy}'. Available: {list(BUILTIN_STRATEGIES.keys())}"}

    strat = BUILTIN_STRATEGIES[strategy]
    signal_fn = strat["signal_fn"]
    exit_fn = strat["exit_fn"]
    max_holding = strat.get("max_holding_days", 252)
    metric_names = strat.get("metrics", [])

    # Default dates: 3 years back
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Get price series for the ticker
    from skills.cvm.calculations.engines.price import price_series

    prices = price_series(ticker, start_date, end_date)
    if not prices:
        return {"status": "not_found",
                "error": f"No price data for '{ticker}' in period {start_date} to {end_date}"}

    # v1.1: Pre-compute signal values ONCE before the loop
    # This calls each metric's *_history() function once (returns ~4-20 data points),
    # then builds a date→value dict for O(1) lookups during the backtest loop.
    # v1.0 called *_at() per day which re-queried the entire DFP+ITR database
    # for each of ~500 trading days = extremely slow.
    signal_data = _precompute_signals(ticker, start_date, end_date, metric_names)

    # Run backtest
    trades: list[dict] = []
    equity_curve: list[dict] = []
    position: dict | None = None
    capital = initial_capital
    peak_equity = initial_capital
    max_drawdown = 0.0
    daily_returns: list[float] = []

    for i, bar in enumerate(prices):
        date = bar["date"]
        price = bar["close"]

        # Check exit conditions
        if position is not None:
            holding_days = i - position["entry_index"]
            should_exit = False
            exit_reason = ""

            if holding_days >= max_holding:
                should_exit = True
                exit_reason = "max_holding"

            if not should_exit:
                try:
                    if exit_fn(date, position["entry_date"], signal_data):
                        should_exit = True
                        exit_reason = "signal"
                except Exception:
                    pass

            if should_exit:
                exit_price = price
                pnl = (exit_price - position["entry_price"]) * position["shares"]
                # Add full proceeds back to cash (not just PnL)
                # Purchase cost was already subtracted when buying.
                # capital = (cash_after_buy) + shares * exit_price
                capital += position["shares"] * exit_price
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": round(position["entry_price"], 2),
                    "exit_date": date,
                    "exit_price": round(exit_price, 2),
                    "shares": position["shares"],
                    "pnl": round(pnl, 2),
                    "return_pct": round((exit_price / position["entry_price"] - 1) * 100, 2),
                    "holding_days": holding_days,
                    "exit_reason": exit_reason,
                })
                position = None

        # Check entry conditions (only if not in position)
        if position is None:
            try:
                if signal_fn(date, signal_data):
                    shares = int(capital / price) if price > 0 else 0
                    if shares > 0:
                        position = {
                            "entry_date": date,
                            "entry_price": price,
                            "shares": shares,
                            "entry_index": i,
                        }
                        capital -= shares * price
            except Exception:
                pass

        # Track equity
        if position is not None:
            equity = capital + position["shares"] * price
        else:
            equity = capital

        equity_curve.append({"date": date, "equity": round(equity, 2)})

        # Track max drawdown
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        # Track daily returns for Sharpe
        if len(equity_curve) >= 2:
            prev_equity = equity_curve[-2]["equity"]
            if prev_equity > 0:
                daily_returns.append(equity / prev_equity - 1)

    # Close any open position at the end
    if position is not None:
        exit_price = prices[-1]["close"]
        pnl = (exit_price - position["entry_price"]) * position["shares"]
        # Add full proceeds back to cash (not just PnL).
        # Purchase cost was already subtracted when buying (line ~346),
        # so we must credit the full sale proceeds here — same logic as the
        # mid-loop exit at line ~320.  Using `+= pnl` here would silently
        # discard the entire cost basis, understating final equity by the
        # full purchase price of any position still open at end-of-period.
        capital += position["shares"] * exit_price
        trades.append({
            "entry_date": position["entry_date"],
            "entry_price": round(position["entry_price"], 2),
            "exit_date": prices[-1]["date"],
            "exit_price": round(exit_price, 2),
            "shares": position["shares"],
            "pnl": round(pnl, 2),
            "return_pct": round((exit_price / position["entry_price"] - 1) * 100, 2),
            "holding_days": len(prices) - 1 - position["entry_index"],
            "exit_reason": "end_of_period",
        })

    # Compute performance metrics
    final_equity = max(capital, 0)  # Guard against negative equity (shouldn't happen but safe)
    total_return = (final_equity / initial_capital - 1) * 100 if initial_capital > 0 else 0

    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = days / 365.25 if days > 0 else 1
    # Guard against complex numbers: (negative) ** fractional = complex in Python
    ratio = final_equity / initial_capital if initial_capital > 0 else 0
    if ratio > 0 and years > 0:
        cagr = (ratio ** (1 / years) - 1) * 100
    else:
        cagr = -100.0  # Total loss

    if daily_returns:
        avg_return = sum(daily_returns) / len(daily_returns)
        std_return = (sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
        sharpe = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
    else:
        sharpe = 0

    winning_trades = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = (winning_trades / len(trades) * 100) if trades else 0

    if prices:
        bh_return = (prices[-1]["close"] / prices[0]["close"] - 1) * 100
    else:
        bh_return = 0

    result = {
        "status": "ok",
        "ticker": ticker,
        "strategy": strategy,
        "strategy_description": strat["description"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "performance": {
            "total_return_pct": round(total_return, 2),
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate_pct": round(win_rate, 1),
            "num_trades": len(trades),
            "buy_hold_return_pct": round(bh_return, 2),
            "alpha_vs_buy_hold": round(total_return - bh_return, 2),
        },
        "trades": trades,
        "equity_curve": equity_curve,
    }

    # [v1.1] Lazy import — was module-level, which bound add_freshness at
    # import time BEFORE the test fixture could patch it. This made backtest
    # tests open 9 real SQLite DBs per call (mock_freshness didn't apply).
    from skills.cvm._freshness import add_freshness
    return add_freshness(result)
