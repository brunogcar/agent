"""skills/cvm/backtest/__init__.py -- Backtest skill manifest + router.

Backtesting engine for CVM strategies. Uses calculations engines + metrics
for signal generation + return computation. Reuses the same engines/metrics
as the historical skill — no data duplication.

Example:
  skill(domain="cvm", sub_domain="backtest", mode="run",
        params='{"ticker":"PETR4","strategy":"value_pe"}')
  skill(domain="cvm", sub_domain="backtest", mode="strategies")
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "backtest",
    "description": (
        "Backtesting engine. run: execute a strategy on a ticker over a date range. "
        "strategies: list available built-in strategies. "
        "results: analyze backtest results (CAGR, Sharpe, max drawdown)."
    ),
    "source":  "COTAHIST (price) + calculations engines/metrics (signals)",
    "storage": "read-only — no own database",
    "modes": {
        "run": {
            "description": "Run a backtest strategy on a single ticker. Returns trades, performance metrics (CAGR, total return, max drawdown, Sharpe ratio, win rate), and equity curve.",
            "include_in_all": True,
            "params": {
                "ticker": "str. B3 ticker (e.g., PETR4). Required.",
                "strategy": "str. Strategy name (value_pe, value_pvpa, quality_roe, quality_roic, income_dy, composite). Default: value_pe.",
                "start_date": "str. Backtest start date (YYYY-MM-DD). Default: 3 years ago.",
                "end_date": "str. Backtest end date (YYYY-MM-DD). Default: today.",
                "initial_capital": "float. Starting capital in BRL. Default: 10000.",
                "max_positions": "int. Max simultaneous positions. Default: 1.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="backtest", mode="run", params=\'{"ticker":"PETR4","strategy":"value_pe"}\')',
                'skill(domain="cvm", sub_domain="backtest", mode="run", params=\'{"ticker":"VALE3","strategy":"composite","start_date":"2022-01-01"}\')',
            ],
        },
        "strategies": {
            "description": "List all available built-in strategies with their descriptions.",
            "include_in_all": False,
            "params": {},
            "examples": [
                'skill(domain="cvm", sub_domain="backtest", mode="strategies")',
            ],
        },
        "results": {
            "description": "Analyze backtest results — extract key metrics for reporting. Takes the dict returned by run() and returns a summary.",
            "include_in_all": False,
            "params": {
                "backtest_result": "dict. The result from run() mode. Required.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="backtest", mode="results", params=\'{"backtest_result": <run result>}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch backtest mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    from skills.cvm.backtest.backtest import run, strategies, results

    dispatch = {
        "run": run,
        "strategies": strategies,
        "results": results,
    }

    fn = dispatch[mode]
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "backtest",
                "mode": mode, "error": str(e)}
