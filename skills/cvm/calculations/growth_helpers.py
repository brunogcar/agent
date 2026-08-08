"""skills/cvm/calculations/growth_helpers.py -- Reusable growth-rate helpers
with period-specific gap tolerance.

[v1.7 review-fix] Period-specific gap-tolerance multipliers.

PROBLEM
-------
Growth metrics (3M / 1Y / 5Y) need a "prior" data point N days back.  In
real CVM data, periods are not perfectly regular:

  - Annual DFP: a company may skip a year (no filing) → the "1Y prior"
    is actually 2Y back.
  - Quarterly ITR: a quarter may be missing → the "3M prior" is 6M back.

The original implementation used a fixed ``max_gap_multiplier = 1.5``
regardless of the lookback window.  That is too loose for 5Y (allows a
data point up to 7.5Y back — distorts CAGR) and too tight for 3M (a
single missed quarter rejects the whole window).

FIX
---
Period-specific multipliers:

  ┌──────────────┬───────────┬──────────────────┬────────────────────────┐
  │ Window       │ Lookback  │ max_gap_mult     │ Max gap (days)         │
  ├──────────────┼───────────┼──────────────────┼────────────────────────┤
  │ 3M           │   90 days │ 1.5  (loose)     │  135 days (~4.5 months)│
  │ 1Y           │  365 days │ 1.5  (loose)     │  547 days (~1.5 years) │
  │ 5Y           │ 1825 days │ 1.2  (tight)     │ 2190 days (~6.0 years) │
  └──────────────┴───────────┴──────────────────┴────────────────────────┘

Rationale:
  - Short windows (3M/1Y): a missed period is common (ITR optional for
    some filers).  1.5x tolerance avoids spurious None.
  - Long windows (5Y): the further back you go, the more the company's
    business may have changed (M&A, spin-offs).  A tight 1.2x tolerance
    prevents comparing against a structurally different era.

USAGE
-----
    from skills.cvm.calculations.growth_helpers import (
        growth_at, growth_history, gap_multiplier_for_lookback,
        LOOKBACK_3M, LOOKBACK_1Y, LOOKBACK_5Y,
    )

    # Point-in-time growth: latest vs ~1Y ago.
    g = growth_at(periods, target_date="2024-06-30", lookback_days=365)

    # Time series of 5Y growth.
    hist = growth_history(periods, lookback_days=1825)

``periods`` is a list of ``{"date": "YYYY-MM-DD", "value": float}`` dicts
sorted oldest-first (duplicates by date are tolerated — last wins).

DESIGN
------
This module is PURE (no DB access, no I/O).  It operates on pre-fetched
``periods`` lists so it can be unit-tested without a database and reused
by both the calculations registry growth metrics AND the financials
dashboard's Crescimento tab (report.py).

The helpers are NOT registered as engines/metrics themselves — they are
building blocks.  Individual growth metrics (revenue_growth,
net_income_growth, etc.) will call ``growth_at`` with their engine's
period list.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta

# ── Lookback windows (days) ──────────────────────────────────────────────────

LOOKBACK_3M = 90
LOOKBACK_1Y = 365
LOOKBACK_5Y = 1825

# ── Period-specific gap-tolerance multipliers ────────────────────────────────
# Maps a lookback (in days) to the max acceptable gap multiplier.  A lookback
# <= 365 days (3M, 1Y) uses the loose 1.5x; a lookback > 365 days (5Y) uses
# the tight 1.2x.  See module docstring for rationale.

_GAP_MULT_SHORT = 1.5   # for lookback <= 365 days (3M / 1Y)
_GAP_MULT_LONG = 1.2    # for lookback >  365 days (5Y)
_GAP_MULT_THRESHOLD_DAYS = 365


def gap_multiplier_for_lookback(lookback_days: int) -> float:
    """Return the period-specific gap-tolerance multiplier for a lookback.

    - lookback <= 365 days → 1.5  (loose; tolerates one missed period)
    - lookback >  365 days → 1.2  (tight; avoids comparing different eras)

    >>> gap_multiplier_for_lookback(90)
    1.5
    >>> gap_multiplier_for_lookback(365)
    1.5
    >>> gap_multiplier_for_lookback(1825)
    1.2
    """
    if lookback_days <= _GAP_MULT_THRESHOLD_DAYS:
        return _GAP_MULT_SHORT
    return _GAP_MULT_LONG


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(d) -> _date:
    """Parse a date string (YYYY-MM-DD) or pass through a date object."""
    if isinstance(d, _date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _period_value(periods: list[dict], target: _date) -> float | None:
    """Get the value for exact target date, or None."""
    for p in periods:
        if _parse_date(p["date"]) == target:
            v = p.get("value")
            return float(v) if v is not None else None
    return None


def _find_latest_on_or_before(periods: list[dict], target: _date) -> dict | None:
    """Most recent period with date <= target AND a non-None value.

    Periods with ``value is None`` (missing data) are skipped so the
    growth computation falls back to the next-most-recent period that
    actually has a figure.
    """
    best: dict | None = None
    best_date: _date | None = None
    for p in periods:
        if p.get("value") is None:
            continue
        d = _parse_date(p["date"])
        if d <= target:
            if best_date is None or d > best_date:
                best = p
                best_date = d
    return best


def _find_prior_within_gap(
    periods: list[dict],
    target: _date,
    lookback_days: int,
    max_gap_multiplier: float | None = None,
) -> dict | None:
    """Find the prior period closest to (target - lookback_days) within gap.

    The "prior" date is ``target - lookback_days``.  We accept any period
    whose date falls in the window::

        [target - lookback_days * max_gap_multiplier,
         target - lookback_days / max_gap_multiplier]

    (symmetric tolerance around the ideal prior date).  Among periods in
    that window with a non-None value, we pick the one CLOSEST to the
    ideal prior date.

    Args:
        periods: list of {"date": str, "value": float|None} dicts.
        target: the "current" date.
        lookback_days: ideal lookback (90 / 365 / 1825).
        max_gap_multiplier: override the period-specific default (None →
            auto-select via gap_multiplier_for_lookback).

    Returns:
        The best-matching period dict (value is guaranteed non-None), or
        None if no period with a value falls within the gap window.
    """
    if max_gap_multiplier is None:
        max_gap_multiplier = gap_multiplier_for_lookback(lookback_days)

    ideal_prior = target - timedelta(days=lookback_days)
    # Symmetric tolerance window around the ideal prior date.
    earliest = target - timedelta(days=int(lookback_days * max_gap_multiplier))
    latest = target - timedelta(days=int(lookback_days / max_gap_multiplier))

    best: dict | None = None
    best_dist: timedelta | None = None
    for p in periods:
        if p.get("value") is None:
            continue  # skip missing-data periods
        d = _parse_date(p["date"])
        if d < earliest or d > latest:
            continue
        dist = abs((d - ideal_prior).days)
        if best_dist is None or dist < best_dist:
            best = p
            best_dist = dist
    return best


# ── Public API ───────────────────────────────────────────────────────────────

def growth_at(
    periods: list[dict],
    target_date: str | _date,
    lookback_days: int,
    max_gap_multiplier: float | None = None,
) -> float | None:
    """Compute growth rate at target_date over a lookback window.

    growth = (current - prior) / |prior|

    - "current" = the most recent period on or before target_date with a
      non-None value.
    - "prior"   = the period closest to (target_date - lookback_days)
      within the gap-tolerance window, with a non-None, non-zero value.

    Returns None if either current or prior is unavailable, or if prior
    is zero (avoids division by zero).

    >>> periods = [
    ...     {"date": "2023-12-31", "value": 100.0},
    ...     {"date": "2024-12-31", "value": 120.0},
    ... ]
    >>> growth_at(periods, "2024-12-31", 365)  # (120-100)/100 = 0.20
    0.2
    """
    if not periods:
        return None

    target = _parse_date(target_date)
    curr_p = _find_latest_on_or_before(periods, target)
    if curr_p is None:
        return None
    curr_val = curr_p.get("value")
    if curr_val is None:
        return None
    curr_val = float(curr_val)

    # Anchor the prior search on the CURRENT period's date, not target_date.
    # When target_date is far beyond the latest available period (e.g. calling
    # growth_at("PETR4", "2026-08-06", 90) when the latest ITR is 2026-03-31),
    # anchoring on target_date makes the symmetric gap window
    # [target - lookback*mult, target - lookback/mult] potentially include the
    # current period itself (2026-03-31 ∈ [2026-03-24, 2026-06-07]).  That would
    # make prior == curr → growth = 0.0 (a false "no growth" reading).
    #
    # Anchoring on curr_p's date guarantees the prior window's upper bound
    # (curr_date - lookback/mult) is strictly before curr_date, so the prior is
    # always an earlier, distinct period — giving the true QoQ/YoY change.
    curr_date = _parse_date(curr_p["date"])
    prior_p = _find_prior_within_gap(
        periods, curr_date, lookback_days, max_gap_multiplier)
    if prior_p is None:
        return None
    # Defensive: prior must be strictly before current (should always hold
    # given the anchoring above, but guard against edge-case equality).
    if _parse_date(prior_p["date"]) >= curr_date:
        return None
    prior_val = prior_p.get("value")
    if prior_val is None or prior_val == 0:
        return None
    prior_val = float(prior_val)

    return (curr_val - prior_val) / abs(prior_val)


def growth_history(
    periods: list[dict],
    lookback_days: int,
    date_from: str | _date | None = None,
    date_to: str | _date | None = None,
    max_gap_multiplier: float | None = None,
) -> list[dict]:
    """Time series of growth rates over a lookback window.

    For each period date in ``periods`` (optionally clamped to
    [date_from, date_to]), compute ``growth_at(periods, date, lookback)``.

    Returns: ``[{"date": str, "growth": float|None, "current": float|None,
    "prior": float|None, "prior_date": str|None}, ...]`` sorted oldest-first.

    The ``prior_date`` field lets callers show WHICH period was used as the
    baseline (useful when gap tolerance selected a non-ideal date).
    """
    if not periods:
        return []

    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None

    if max_gap_multiplier is None:
        max_gap_multiplier = gap_multiplier_for_lookback(lookback_days)

    result: list[dict] = []
    for p in sorted(periods, key=lambda x: _parse_date(x["date"])):
        d = _parse_date(p["date"])
        if df and d < df:
            continue
        if dt and d > dt:
            continue

        curr_val = p.get("value")
        target = d

        prior_p = _find_prior_within_gap(
            periods, target, lookback_days, max_gap_multiplier)
        prior_val = prior_p.get("value") if prior_p else None
        prior_date = prior_p["date"] if prior_p else None

        growth = None
        if (curr_val is not None and prior_val is not None
                and prior_val != 0):
            growth = (float(curr_val) - float(prior_val)) / abs(float(prior_val))

        result.append({
            "date": p["date"],
            "growth": growth,
            "current": float(curr_val) if curr_val is not None else None,
            "prior": float(prior_val) if prior_val is not None else None,
            "prior_date": prior_date,
        })
    return result


# ── CAGR (Compound Annual Growth Rate) ──────────────────────────────────────

def cagr_at(
    periods: list[dict],
    target_date: str | _date,
    years: int,
    max_gap_multiplier: float | None = None,
) -> float | None:
    """Compute CAGR (Compound Annual Growth Rate) at target_date.

    CAGR = (end / start) ^ (1 / years) - 1

    Unlike growth_at() which computes simple point-to-point % change,
    CAGR gives the annualized compounded rate — the constant rate that
    would take you from start to end over N years.

    Args:
        periods: list of {"date": str, "value": float|None} sorted oldest-first.
        target_date: the "end" date (current period).
        years: number of years to look back (1, 3, 5, 10, etc.).
        max_gap_multiplier: override the period-specific default.

    Returns:
        CAGR as a fraction (0.085 = 8.5% annualized), or None if either
        start or end value is unavailable, or if start <= 0 (CAGR
        undefined for negative/zero base).

    >>> periods = [
    ...     {"date": "2019-12-31", "value": 100.0},
    ...     {"date": "2024-12-31", "value": 150.0},
    ... ]
    >>> cagr_at(periods, "2024-12-31", years=5)
    0.08447177119768055  # (150/100)^(1/5) - 1 ≈ 8.45%
    """
    target = _parse_date(target_date)

    # Find the current (end) value
    curr_p = _find_latest_on_or_before(periods, target)
    if curr_p is None:
        return None
    end_val = curr_p.get("value")
    if end_val is None or end_val <= 0:
        return None  # CAGR undefined for negative/zero base

    # Find the start value (N years back)
    lookback_days = years * 365
    if max_gap_multiplier is None:
        max_gap_multiplier = gap_multiplier_for_lookback(lookback_days)

    start_p = _find_prior_within_gap(
        periods, target, lookback_days, max_gap_multiplier)
    if start_p is None:
        return None
    start_val = start_p.get("value")
    if start_val is None or start_val <= 0:
        return None

    # CAGR = (end / start) ^ (1 / years) - 1
    ratio = end_val / start_val
    if ratio <= 0:
        return None

    return ratio ** (1.0 / years) - 1.0


def cagr_history(
    periods: list[dict],
    years: int,
    date_from: str | _date | None = None,
    date_to: str | _date | None = None,
    max_gap_multiplier: float | None = None,
) -> list[dict]:
    """Time series of CAGR over N years.

    For each period date, computes CAGR looking back `years` years.

    Returns: [{"date": str, "cagr": float|None, "end_value": float|None,
    "start_value": float|None, "start_date": str|None}, ...] sorted oldest-first.
    """
    if not periods:
        return []

    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None

    if max_gap_multiplier is None:
        max_gap_multiplier = gap_multiplier_for_lookback(years * 365)

    result: list[dict] = []
    for p in sorted(periods, key=lambda x: _parse_date(x["date"])):
        d = _parse_date(p["date"])
        if df and d < df:
            continue
        if dt and d > dt:
            continue

        end_val = p.get("value")

        start_p = _find_prior_within_gap(
            periods, d, years * 365, max_gap_multiplier)
        start_val = start_p.get("value") if start_p else None
        start_date = start_p["date"] if start_p else None

        cagr = None
        if (end_val is not None and end_val > 0
            and start_val is not None and start_val > 0):
            ratio = end_val / start_val
            if ratio > 0:
                cagr = ratio ** (1.0 / years) - 1.0

        result.append({
            "date": p["date"],
            "cagr": cagr,
            "end_value": float(end_val) if end_val is not None else None,
            "start_value": float(start_val) if start_val is not None else None,
            "start_date": start_date,
        })
    return result


# ── DCF/IRR helpers (v2.1) ───────────────────────────────────────────────────
# Moved here to avoid circular imports between dcf_intrinsic_value.py and irr.py

DEFAULT_TERMINAL_GROWTH = 0.04  # 4% — below long-term IPCA average (~5-6%)
PROJECTION_YEARS = 5


def get_terminal_growth() -> float:
    """Get terminal growth rate from IPCA 12M accumulated.

    Uses BCB SGS series 433 (IPCA monthly). Accumulates last 12 months
    to get annual IPCA. Falls back to DEFAULT_TERMINAL_GROWTH if unavailable.
    """
    try:
        from data_sources.bcb.sgs.query_engine import series
        res = series(code=433, days=400)
        if res.get("status") == "ok":
            obs = res.get("observations", [])
            if len(obs) >= 12:
                product = 1.0
                for o in obs[-12:]:
                    v = o.get("value")
                    if v is not None:
                        product *= (1.0 + float(v) / 100.0)
                ipca_12m = product - 1.0
                return min(ipca_12m, 0.08)  # Cap at 8%
    except Exception:
        pass
    return DEFAULT_TERMINAL_GROWTH


def project_fcf(base_fcf: float, growth_rate: float, years: int) -> list[float]:
    """Project FCF for N years using a growth rate. Caps growth at -10% to +30%."""
    capped_growth = min(max(growth_rate, -0.10), 0.30)
    projections = []
    for t in range(1, years + 1):
        projections.append(base_fcf * (1.0 + capped_growth) ** t)
    return projections
