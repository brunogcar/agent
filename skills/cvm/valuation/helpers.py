"""skills/cvm/valuation/helpers.py -- Shared utilities for valuation modes.

Holds cross-mode helpers used by the fetchers (fetchers.py) and the mode
implementations (modes/*.py). Kept dependency-light so importing it does NOT
trigger calculations-engine imports (those require PLANNER_MODEL env var via
skills.cvm.calculations.*).

Public helpers:
  - _safe_call : wraps a callable in try/except -> None on any error.
  - _safe_div  : divides a/b, returning None when either side is None or b is 0.
"""
from __future__ import annotations

from typing import Callable


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_call(fn: Callable, *args, **kwargs):
    """Call a calculations engine/metric, return None on any exception.

    Calculations engines raise FileNotFoundError when their backing DB is not
    synced (e.g., ITR db missing in test environments). Wrap each call so one
    missing engine doesn't poison the rest of the ratios() result.
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    """Divide a/b, returning None when either side is None or b is zero.

    Used by the manual ratio computations in ratios() (market_cap / lucro_liquido,
    etc.). Calculations metrics handle None internally, but the manual ratios
    that compose brapi_market_cap + investsite fallback still need this helper.
    """
    if a is None or b is None or b == 0:
        return None
    return a / b
