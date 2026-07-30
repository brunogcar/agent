"""skills/cvm/backtest/helpers.py -- Shared signal + strategy helpers.

Each strategy declares which calculations metrics it needs (e.g. ``["pe"]``).
Before the backtest loop, ``run()`` calls ``_precompute_signals()`` ONCE per
metric to get the full date→value series (step-function optimization --
v1.0 called ``*_at()`` per day which re-queried DFP+ITR for each of ~500
trading days). During the loop, ``_lookup_signal()`` does O(1) lookups
against the pre-computed series.

This module is dependency-light: it only imports ``importlib`` lazily inside
``_precompute_signals()`` so importing it does NOT trigger the calculations
engines.
"""
from __future__ import annotations

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
