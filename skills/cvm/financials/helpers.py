"""skills/cvm/financials/helpers.py -- Shared utilities for financials modes.

Holds cross-mode helpers used by both the fetchers (fetchers.py) and the
mode implementations (modes/*.py). Kept dependency-light so importing it
does NOT trigger calculations-engine imports (those require PLANNER_MODEL
env var via skills.cvm.calculations.*).

Public helpers:
  - _safe_call           : wraps a callable in try/except → None on any error.
  - _compute_ttm_section : builds the TTM section of a quarterly response.
"""
from __future__ import annotations

from typing import Callable

from skills.cvm.financials.metrics import compute_ttm, compute_ttm_with_engines


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_call(fn: Callable, *args, **kwargs):
    """Call a calculations engine/metric and return None on any error.

    Calculations engines call connect_dfp/connect_itr/connect_fre/cotahist,
    each of which may raise FileNotFoundError when the underlying DB is not
    synced. Many engines also need optional accounts (e.g. tax 3.08, cash
    1.01.01) that may not be filed for every company. Without this wrapper,
    one missing DB or account would crash the entire summary() call.
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


# Maps a quarter number (1-4) to its calendar end-date suffix (MM-DD).
_QUARTER_END_SUFFIX = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def _compute_ttm_section(company: str, result_periods: list[dict]) -> dict:
    """Build the TTM section of the quarterly response.

    [v1.3 migration] Uses compute_ttm_with_engines() to delegate TTM flow
    metrics (revenue, ebit, da, earnings, FCO/FCI/FCF, EBITDA) to the
    calculations engines instead of summing 4 standalone quarters. Snapshot
    metrics continue to use 4-quarter averaging inside compute_ttm_with_engines.

    Falls back to the legacy compute_ttm() (sum-of-4-quarters) when:
      - `company` is empty (defensive — should never happen in practice)
      - `result_periods` has no quarter info we can derive an end-date from
      - compute_ttm_with_engines raises (shouldn't happen — engines are
        wrapped in _safe_engine_call internally, but defensive nonetheless)

    Args:
        company: Ticker, name, or CNPJ (passed through to calculations engines).
        result_periods: list of period dicts (sorted oldest-first) with at
            least `year` and `quarter` keys on each entry.

    Returns:
        TTM dict shaped like {status, period_range, metrics, ratios} or
        {status: "insufficient_data"} when fewer than 4 quarters are present.
    """
    if not company or not result_periods:
        return compute_ttm(result_periods)

    # Derive the latest quarter's end date (TTM window ends here).
    latest = result_periods[-1]  # oldest-first → last is newest
    year = latest.get("year")
    qnum = latest.get("quarter")
    if year is None or qnum not in _QUARTER_END_SUFFIX:
        return compute_ttm(result_periods)
    ttm_date = f"{year}-{_QUARTER_END_SUFFIX[qnum]}"

    try:
        return compute_ttm_with_engines(company, ttm_date, result_periods)
    except Exception:
        # Defensive: engines are wrapped in _safe_engine_call inside
        # compute_ttm_with_engines, but if anything slips through, fall back
        # to the legacy sum-of-4-quarters derivation.
        return compute_ttm(result_periods)
