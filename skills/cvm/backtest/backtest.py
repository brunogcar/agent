"""skills/cvm/backtest/backtest.py -- Backtesting engine for CVM strategies.

Uses calculations engines + metrics for signal generation + return computation.
Reuses the same engines/metrics as the historical skill — no data duplication.

v1.1: Pre-computes signal values ONCE before the backtest loop using metric
*_history() functions (step-function optimization). v1.0 called *_at() per
day which re-queried the entire DFP+ITR database for each of ~500 trading days.

MODES
-----
  run       -- run a backtest strategy over a date range
  strategies -- list available built-in strategies
  results   -- analyze backtest results (CAGR, Sharpe, max drawdown)

NO SYNC
-------
Read-only. Assumes COTAHIST + DFP + ITR + FRE are already synced.

STRATEGY FORMAT
---------------
A strategy is a dict with:
  - name: str
  - description: str
  - metrics: list of metric names to pre-compute (e.g., ["pe", "roe"])
  - signal_fn: function(date, signal_data) -> bool  (buy signal, uses pre-computed data)
  - exit_fn: function(date, entry_date, signal_data) -> bool  (sell signal, optional)
  - max_holding_days: int (optional, default 252 = 1 year)

Built-in strategies use calculations metrics:
  - value_pe: buy when P/L < 5 (cheap)
  - value_pvpa: buy when P/VPA < 1.0 (cheap)
  - quality_roe: buy when ROE > 0.20 (high return on equity)
  - quality_roic: buy when ROIC > 0.15 (high return on invested capital)
  - income_dy: buy when Div Yield > 0.06 (high dividend yield)
  - composite: buy when P/L < 8 AND ROE > 0.15 (value + quality)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from skills.cvm._freshness import add_freshness


# ── Signal data pre-computation ──────────────────────────────────────────────
# Each strategy declares which metrics it needs. Before the backtest loop,
# we call the metric's *_history() function ONCE to get the full series,
# then build a date→value lookup dict for O(1) access during the loop.

_SIGNAL_METRIC_HISTORY = {
    "pe": "skills.cvm.calculations.metrics.lpa.lpa_history",
    "pvpa": "skills.cvm.calculations.metrics.vpa.vpa_history",
    "roe": "skills.cvm.calculations.metrics.roe.roe_history",
    "roic": "skills.cvm.calculations.metrics.roic.roic_history",
    "dy": "skills.cvm.calculations.metrics.dpa.dpa_history",
}

_SIGNAL_METRIC_KEY = {
    "pe": "pe",
    "pvpa": "pvpa",
    "roe": "roe",
    "roic": "roic",
    "dy": "dy",
}


def _precompute_signals(ticker: str, start_date: str, end_date: str,
                        metric_names: list[str]) -> dict[str, dict[str, float]]:
    """Pre-compute signal values for the entire backtest period.

    Calls each metric's *_history() function ONCE, builds a date→value dict.

    Returns: {"pe": {"2023-01-15": 4.5, ...}, "roe": {"2023-01-15": 0.28, ...}}
    """
    import importlib

    result: dict[str, dict[str, float]] = {}
    for metric_name in metric_names:
        if metric_name not in _SIGNAL_METRIC_HISTORY:
            continue
        module_path = _SIGNAL_METRIC_HISTORY[metric_name]
        module_name, func_name = module_path.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_name)
            history_fn = getattr(mod, func_name)
            series = history_fn(ticker, start_date, end_date)
            value_key = _SIGNAL_METRIC_KEY[metric_name]
            date_to_value: dict[str, float] = {}
            for entry in series:
                val = entry.get(value_key)
                if val is not None and val > 0:
                    date_to_value[entry["date"]] = val
            result[metric_name] = date_to_value
        except Exception:
            result[metric_name] = {}
    return result


def _lookup_signal(signal_data: dict[str, dict[str, float]],
                   metric_name: str, date: str) -> float | None:
    """O(1) lookup of pre-computed signal value for a given date.

    If the exact date isn't in the dict, finds the most recent date <= the
    target date (step-function behavior).
    """
    date_map = signal_data.get(metric_name, {})
    if not date_map:
        return None
    # Exact match
    if date in date_map:
        return date_map[date]
    # Find most recent date <= target
    candidates = [d for d in date_map if d <= date]
    if not candidates:
        return None
    latest = max(candidates)
    return date_map[latest]


# ── Built-in strategies ──────────────────────────────────────────────────────
# Each strategy declares:
# - metrics: which pre-computed signals it needs
# - signal_fn: takes (date, signal_data) -> bool, uses _lookup_signal for O(1) access

def _signal_value_pe(date: str, signal_data: dict) -> bool:
    """Buy when P/L < 5."""
    pe = _lookup_signal(signal_data, "pe", date)
    return pe is not None and pe > 0 and pe < 5.0


def _signal_value_pvpa(date: str, signal_data: dict) -> bool:
    """Buy when P/VPA < 1.0."""
    pvpa = _lookup_signal(signal_data, "pvpa", date)
    return pvpa is not None and pvpa > 0 and pvpa < 1.0


def _signal_quality_roe(date: str, signal_data: dict) -> bool:
    """Buy when ROE > 20%."""
    roe = _lookup_signal(signal_data, "roe", date)
    return roe is not None and roe > 0.20


def _signal_quality_roic(date: str, signal_data: dict) -> bool:
    """Buy when ROIC > 15%."""
    roic = _lookup_signal(signal_data, "roic", date)
    return roic is not None and roic > 0.15


def _signal_income_dy(date: str, signal_data: dict) -> bool:
    """Buy when Dividend Yield > 6%."""
    dy = _lookup_signal(signal_data, "dy", date)
    return dy is not None and dy > 0.06


def _signal_composite(date: str, signal_data: dict) -> bool:
    """Buy when P/L < 8 AND ROE > 15%."""
    pe = _lookup_signal(signal_data, "pe", date)
    roe = _lookup_signal(signal_data, "roe", date)
    return (pe is not None and pe > 0 and pe < 8.0
            and roe is not None and roe > 0.15)


def _exit_default(date: str, entry_date: str, signal_data: dict) -> bool:
    """Default exit: hold for max_holding_days (handled by run loop)."""
    return False


BUILTIN_STRATEGIES: dict[str, dict] = {
    "value_pe": {
        "name": "value_pe",
        "description": "Buy when P/L < 5 (cheap valuation)",
        "metrics": ["pe"],
        "signal_fn": _signal_value_pe,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
    "value_pvpa": {
        "name": "value_pvpa",
        "description": "Buy when P/VPA < 1.0 (trading below book value)",
        "metrics": ["pvpa"],
        "signal_fn": _signal_value_pvpa,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
    "quality_roe": {
        "name": "quality_roe",
        "description": "Buy when ROE > 20% (high return on equity)",
        "metrics": ["roe"],
        "signal_fn": _signal_quality_roe,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
    "quality_roic": {
        "name": "quality_roic",
        "description": "Buy when ROIC > 15% (high return on invested capital)",
        "metrics": ["roic"],
        "signal_fn": _signal_quality_roic,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
    "income_dy": {
        "name": "income_dy",
        "description": "Buy when Dividend Yield > 6% (high income)",
        "metrics": ["dy"],
        "signal_fn": _signal_income_dy,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
    "composite": {
        "name": "composite",
        "description": "Buy when P/L < 8 AND ROE > 15% (value + quality)",
        "metrics": ["pe", "roe"],
        "signal_fn": _signal_composite,
        "exit_fn": _exit_default,
        "max_holding_days": 252,
    },
}


# ── Mode: run ────────────────────────────────────────────────────────────────

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

    return add_freshness(result)


# ── Mode: strategies ─────────────────────────────────────────────────────────

def strategies() -> dict:
    """List all available built-in strategies."""
    result = {
        "status": "ok",
        "strategies": [
            {
                "name": s["name"],
                "description": s["description"],
                "max_holding_days": s.get("max_holding_days", 252),
                "metrics": s.get("metrics", []),
            }
            for s in BUILTIN_STRATEGIES.values()
        ],
        "count": len(BUILTIN_STRATEGIES),
    }
    return result


# ── Mode: results ────────────────────────────────────────────────────────────

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
