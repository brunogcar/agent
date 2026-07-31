"""skills/cvm/calculations/growth_helpers.py -- Shared helpers for growth metrics.

Growth metrics compare the SAME engine's value at two different dates:
  growth = (value_at_latest - value_at_lookback) / |value_at_lookback|

This is a different pattern from existing fundamental ratios which compare
two DIFFERENT engines at the SAME date. The helpers here handle the lookback
logic shared by all growth metrics (revenue_growth, gross_profit_growth,
net_income_growth).

Lookback horizons (matching the private spreadsheet):
  - 3M: 90 days back (quarter-over-quarter TTM change)
  - 1Y: 365 days back (year-over-year)
  - 5Y: 1825 days back (5-year growth)

GAP TOLERANCE (added v1.8):
  When the engine's most recent period at or before the lookback date is
  STALE (much older than the requested lookback horizon), the growth
  number is misleading. For example, requesting 1Y growth but only
  having 2Y-old data would yield a misleading growth figure that's
  actually 2Y growth. We mitigate this by rejecting "old" values whose
  date is more than ``lookback_days * max_gap_multiplier`` days before
  the lookback date (default multiplier = 1.5).

  - 3M horizon (90 days): reject old value if it's > 135 days before
    the lookback date.
  - 1Y horizon (365 days): reject if > 547 days before.
  - 5Y horizon (1825 days): reject if > 2737 days before.

  Without the gap tolerance, a metric like revenue_growth_1y_at() would
  return a number based on the most recent period ≤ the 365-day-ago
  date, even if that period is 2+ years old (e.g., for a company that
  recently stopped filing). The number would silently misrepresent the
  growth horizon. With the gap tolerance, such cases return None
  instead, surfacing the data gap rather than hiding it.

Usage:
    from skills.cvm.calculations.growth_helpers import growth_at, growth_history

    # In a metric file:
    def revenue_growth_1y_at(company, date):
        return growth_at(company, date, revenue_periods, "ttm_rev", 365)

    def revenue_growth_1y_history(company, date_from, date_to):
        return growth_history(company, date_from, date_to,
                              revenue_periods, "ttm_rev", 365,
                              "revenue_growth_1y")
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable


def _find_value_at_or_before(
    periods: list[dict],
    target_date: str,
    value_key: str,
) -> float | None:
    """Find the engine value at or before target_date.

    Args:
        periods: List of {"date": "YYYY-MM-DD", value_key: float} sorted oldest-first.
        target_date: The date to look up (YYYY-MM-DD).
        value_key: The dict key holding the value (e.g. "ttm_rev", "ttm_gp", "ttm").

    Returns:
        The value at the most recent period <= target_date, or None if no
        period exists before target_date.
    """
    result = None
    for p in periods:
        if p["date"] <= target_date:
            result = p.get(value_key)
        else:
            break
    return result


def _find_value_and_date_at_or_before(
    periods: list[dict],
    target_date: str,
    value_key: str,
) -> tuple[float | None, str | None]:
    """Find (value, date) at or before target_date.

    Same as `_find_value_at_or_before` but also returns the matched
    period's date — used by gap-tolerance checks in `growth_at` and
    `growth_history`.

    Returns:
        (value, date) tuple. Both None if no period exists before target_date.
    """
    result_value = None
    result_date = None
    for p in periods:
        if p["date"] <= target_date:
            result_value = p.get(value_key)
            result_date = p["date"]
        else:
            break
    return result_value, result_date


def growth_at(
    company: str,
    date: str,
    periods_fn: Callable,
    value_key: str,
    lookback_days: int,
    max_gap_multiplier: float = 1.5,
) -> float | None:
    """Compute growth = (latest - old) / |old| for a given lookback period.

    Args:
        company: Ticker, name, or CNPJ.
        date: The reference date (YYYY-MM-DD). Growth is measured from
              (date - lookback_days) to date.
        periods_fn: The engine's _periods() function (e.g. revenue_periods).
        value_key: The dict key in period entries holding the value
                   (e.g. "ttm_rev", "ttm_gp", "ttm").
        lookback_days: How many days back to compare (90=3M, 365=1Y, 1825=5Y).
        max_gap_multiplier: Reject the "old" value if it's more than
                            ``lookback_days * max_gap_multiplier`` days before
                            the lookback date (default 1.5 — see module
                            docstring for rationale).

    Returns:
        Growth as a fraction (0.15 = 15% growth, -0.05 = 5% decline),
        or None if either value is missing, the old value is zero, OR
        the old value's date is too far before the lookback date
        (gap-tolerance check).
    """
    periods = periods_fn(company)
    if not periods:
        return None

    # Get the "latest" value at or before `date`
    latest = _find_value_at_or_before(periods, date, value_key)
    if latest is None:
        return None

    # Compute the lookback date
    try:
        dt = datetime.fromisoformat(date[:10])
    except (ValueError, TypeError):
        return None
    lookback_date = (dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # Get the "old" value at or before the lookback date (and its actual date)
    old, old_date = _find_value_and_date_at_or_before(periods, lookback_date, value_key)
    if old is None or old == 0:
        return None

    # Gap-tolerance check: if old_date is too far before the lookback date,
    # the "old" value is stale and the growth number would misrepresent the
    # requested horizon. Return None to surface the data gap.
    if old_date is not None and max_gap_multiplier > 0:
        try:
            old_dt = datetime.fromisoformat(old_date[:10])
            gap_days = (datetime.fromisoformat(lookback_date[:10]) - old_dt).days
            max_gap_days = lookback_days * max_gap_multiplier
            if gap_days > max_gap_days:
                return None
        except (ValueError, TypeError):
            # If we can't parse dates, fall through and compute growth anyway.
            pass

    return (latest - old) / abs(old)


def growth_history(
    company: str,
    date_from: str,
    date_to: str,
    periods_fn: Callable,
    value_key: str,
    lookback_days: int,
    growth_key: str,
    max_gap_multiplier: float = 1.5,
) -> list[dict]:
    """Compute growth time series across all engine periods in [date_from, date_to].

    For each period date in the range, computes growth vs (date - lookback_days).

    Args:
        company: Ticker.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).
        periods_fn: The engine's _periods() function.
        value_key: The dict key in period entries holding the value.
        lookback_days: How many days back to compare.
        growth_key: The key to use for the growth value in the output dicts
                    (e.g. "revenue_growth_1y").
        max_gap_multiplier: Reject the "old" value if it's more than
                            ``lookback_days * max_gap_multiplier`` days before
                            the lookback date (default 1.5 — see module
                            docstring for rationale).

    Returns:
        List of {"date", growth_key, "value", "old_value", "old_date"}
        sorted oldest-first. Entries where growth can't be computed (missing
        old value, zero old value, OR stale old value past the gap-tolerance
        threshold) are included with growth_key=None.
    """
    periods = periods_fn(company)
    if not periods:
        return []

    result = []
    for p in periods:
        date = p["date"]
        if date < date_from or date > date_to:
            continue

        value = p.get(value_key)
        if value is None:
            continue

        # Compute lookback date
        try:
            dt = datetime.fromisoformat(date[:10])
        except (ValueError, TypeError):
            continue
        lookback_date = (dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        old, old_date = _find_value_and_date_at_or_before(periods, lookback_date, value_key)

        growth = None
        if old is not None and old != 0:
            # Gap-tolerance check: skip growth computation if old_date is too
            # far before the lookback date (stale data — see module docstring).
            stale = False
            if old_date is not None and max_gap_multiplier > 0:
                try:
                    old_dt = datetime.fromisoformat(old_date[:10])
                    gap_days = (datetime.fromisoformat(lookback_date[:10]) - old_dt).days
                    max_gap_days = lookback_days * max_gap_multiplier
                    if gap_days > max_gap_days:
                        stale = True
                except (ValueError, TypeError):
                    pass
            if not stale:
                growth = (value - old) / abs(old)

        entry = {
            "date": date,
            growth_key: growth,
            "value": value,
            "old_value": old,
            "old_date": old_date,
        }
        result.append(entry)

    return result
