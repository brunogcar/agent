"""engines/beta.py -- Beta (5Y) engine via rolling regression vs IBOV.

Beta = Cov(R_stock, R_ibov) / Var(R_ibov)

[v4] REVIEW FIXES:
  - P0: Split beta_at() (returns float) from beta_stats_at() (returns dict).
  - P0: beta_periods() fetches stock + IBOV prices ONCE, then slices windows
    in-memory. Was 660+ DB round-trips, now 2.
  - P1: Fixed Feb 29 leap year crash: timedelta instead of .replace(year=).
  - P2: COTAHIST fallback queries B3 index DB for top IBOV constituents
    dynamically (was hardcoded list).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from skills._base import engine_cached


def _fetch_stock_returns(ticker: str, end_date: str, years: int = 5) -> dict[str, float]:
    """Fetch daily returns for a stock from COTAHIST."""
    from skills.cvm.calculations.engines.price import price_series

    # [v4 P1] Use timedelta, not .replace(year=...), to avoid Feb 29 crash
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")

    prices = price_series(ticker, start_date, end_date)
    if len(prices) < 60:
        return {}

    returns = {}
    for i in range(1, len(prices)):
        prev_close = prices[i - 1]["close"]
        curr_close = prices[i]["close"]
        if prev_close and prev_close > 0 and curr_close:
            returns[prices[i]["date"]] = (curr_close / prev_close) - 1.0
    return returns


def _fetch_ibov_returns(end_date: str, years: int = 5) -> dict[str, float]:
    """Fetch daily returns for IBOV. Tries brapi ^BVSP, falls back to COTAHIST proxy."""
    # Path 1: Try brapi ^BVSP
    try:
        from data_sources.b3.brapi.fetcher import fetch_history
        result = fetch_history("^BVSP", range=f"{years}y", interval="1d")
        if result.get("status") == "ok":
            ohlcv = result.get("ohlcv", [])
            if len(ohlcv) >= 60:
                returns = {}
                prev_close = None
                for bar in ohlcv:
                    date_str = bar.get("date", "")
                    close = bar.get("close")
                    if not date_str or not close:
                        continue
                    if date_str > end_date:
                        break
                    if prev_close and prev_close > 0:
                        returns[date_str] = (close / prev_close) - 1.0
                    prev_close = close
                if len(returns) >= 60:
                    return returns
    except Exception:
        pass

    # Path 2: Fallback via COTAHIST proxy
    return _fetch_ibov_proxy_from_cotahist(end_date, years)


def _get_top_ibov_constituents() -> list[str]:
    """Get top IBOV constituents from B3 index DB.

    [v4 P2] Queries data_sources.b3.index dynamically instead of hardcoding.
    Falls back to a hardcoded list if the index DB is not synced.
    """
    try:
        from data_sources.b3.index.catalog import connect as index_connect
        from data_sources.b3.index.catalog import db_path as index_db_path
        path = index_db_path()
        if path.exists():
            conn = index_connect(read_only=True)
            rows = conn.execute(
                """SELECT ticker FROM index_constituents
                   WHERE index_code = 'IBOV'
                     AND ref_date = (SELECT MAX(ref_date) FROM index_constituents WHERE index_code = 'IBOV')
                   ORDER BY participation DESC LIMIT 10"""
            ).fetchall()
            conn.close()
            if rows:
                return [r["ticker"] for r in rows]
    except Exception:
        pass

    # Fallback: hardcoded top 10 (stable, changes only quarterly)
    return ["PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3",
            "ABEV3", "B3SA3", "MGLU3", "RENT3", "WEGE3"]


def _fetch_ibov_proxy_from_cotahist(end_date: str, years: int = 5) -> dict[str, float]:
    """Compute IBOV proxy returns from top constituents via COTAHIST."""
    from skills.cvm.calculations.engines.price import price_series

    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")
    ibov_top = _get_top_ibov_constituents()

    all_series: dict[str, dict[str, float]] = {}
    for ticker in ibov_top:
        prices = price_series(ticker, start_date, end_date)
        if len(prices) >= 60:
            all_series[ticker] = {p["date"]: p["close"] for p in prices}

    if len(all_series) < 5:
        return {}

    all_dates = set()
    for series in all_series.values():
        all_dates.update(series.keys())
    all_dates = sorted(all_dates)

    returns = {}
    prev_avg = None
    for date in all_dates:
        closes = [s[date] for s in all_series.values() if date in s]
        if len(closes) < 3:
            continue
        avg_close = sum(closes) / len(closes)
        if prev_avg and prev_avg > 0:
            returns[date] = (avg_close / prev_avg) - 1.0
        prev_avg = avg_close
    return returns


def _ols_regression(stock_returns: list[float], ibov_returns: list[float]) -> dict:
    """Simple OLS regression: y = alpha + beta * x."""
    n = len(stock_returns)
    if n < 30:
        return {"beta": None, "alpha": None, "r_squared": None}

    sum_x = sum(ibov_returns)
    sum_y = sum(stock_returns)
    sum_xy = sum(x * y for x, y in zip(ibov_returns, stock_returns))
    sum_x2 = sum(x * x for x in ibov_returns)
    sum_y2 = sum(y * y for y in stock_returns)

    mean_x = sum_x / n
    mean_y = sum_y / n

    cov_xy = (sum_xy / n) - (mean_x * mean_y)
    var_x = (sum_x2 / n) - (mean_x * mean_x)
    var_y = (sum_y2 / n) - (mean_y * mean_y)

    if var_x == 0 or var_x < 1e-15:
        return {"beta": None, "alpha": None, "r_squared": None}

    beta = cov_xy / var_x
    alpha = mean_y - beta * mean_x

    if var_y < 1e-15:
        r_squared = 0.0
    else:
        r_squared = (cov_xy * cov_xy) / (var_x * var_y) if var_x > 0 else 0.0

    return {"beta": beta, "alpha": alpha, "r_squared": r_squared}


@engine_cached
def beta_stats_at(company: str, date: str) -> dict | None:
    """Compute 5Y Beta regression stats at or before a given date.

    Returns:
        {"beta": 1.15, "alpha": 0.0001, "r_squared": 0.65, "n": 1250}
        or None if insufficient data.
    """
    stock_returns = _fetch_stock_returns(company, date, years=5)
    ibov_returns = _fetch_ibov_returns(date, years=5)

    if not stock_returns or not ibov_returns:
        return None

    common_dates = sorted(set(stock_returns.keys()) & set(ibov_returns.keys()))
    if len(common_dates) < 60:
        return None

    aligned_stock = [stock_returns[d] for d in common_dates]
    aligned_ibov = [ibov_returns[d] for d in common_dates]

    result = _ols_regression(aligned_stock, aligned_ibov)
    if result["beta"] is None:
        return None

    result["n"] = len(common_dates)
    return result


@engine_cached
def beta_at(company: str, date: str) -> float | None:
    """Get 5Y Beta (rolling regression vs IBOV) at or before a given date.

    [v4 P0] Returns just the beta float (was returning a dict). The full
    regression stats (alpha, r_squared) are available via beta_stats_at().

    Args:
        company: B3 ticker (PETR4).
        date: YYYY-MM-DD (end date for the 5Y window).

    Returns:
        Beta as a float (e.g., 1.15), or None if insufficient data.
    """
    stats = beta_stats_at(company, date)
    if stats is None:
        return None
    return stats.get("beta")


@engine_cached
def beta_periods(company: str) -> list[dict]:
    """Get all Beta periods for a company (monthly sampling).

    [v4 P0] PERFORMANCE FIX: Fetches stock + IBOV prices ONCE, then computes
    rolling 1Y regression windows in-memory. Was 660+ DB round-trips, now 2.

    Returns list of {"date": ..., "beta": float, "r_squared": float} sorted oldest-first.
    """
    # [v4 P1] Use timedelta, not .replace(year=...), to avoid Feb 29 crash
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=5 * 365 + 30)).strftime("%Y-%m-%d")

    # Fetch stock prices ONCE
    from skills.cvm.calculations.engines.price import price_series
    stock_prices = price_series(company, start_date, end_date)
    if len(stock_prices) < 60:
        return []

    # Compute stock returns ONCE
    stock_returns = {}
    for i in range(1, len(stock_prices)):
        prev = stock_prices[i - 1]["close"]
        curr = stock_prices[i]["close"]
        if prev and prev > 0 and curr:
            stock_returns[stock_prices[i]["date"]] = (curr / prev) - 1.0

    # Fetch IBOV returns ONCE
    ibov_returns = _fetch_ibov_returns(end_date, years=5)
    if not ibov_returns or len(ibov_returns) < 60:
        return []

    # Build aligned return series (sorted by date)
    common_dates = sorted(set(stock_returns.keys()) & set(ibov_returns.keys()))
    if len(common_dates) < 60:
        return []

    aligned_stock = [stock_returns[d] for d in common_dates]
    aligned_ibov = [ibov_returns[d] for d in common_dates]

    # Sample monthly: take the last trading day of each month
    monthly_indices = []
    seen_months = set()
    for i in range(len(common_dates) - 1, -1, -1):
        month_key = common_dates[i][:7]
        if month_key not in seen_months:
            seen_months.add(month_key)
            monthly_indices.append(i)
    monthly_indices.reverse()

    # For each monthly checkpoint, compute rolling 1Y beta from pre-fetched data
    periods = []
    min_window = 60

    for idx in monthly_indices:
        checkpoint_date = common_dates[idx]

        # Find the start index for the 1Y window (approx 252 trading days back)
        window_start = max(0, idx - 252)
        window_size = idx - window_start + 1

        if window_size < min_window:
            continue

        # Slice the pre-fetched returns
        window_stock = aligned_stock[window_start:idx + 1]
        window_ibov = aligned_ibov[window_start:idx + 1]

        result = _ols_regression(window_stock, window_ibov)
        if result["beta"] is not None:
            periods.append({
                "date": checkpoint_date,
                "beta": result["beta"],
                "r_squared": result.get("r_squared"),
            })

    return periods


# -- Register with the engine registry ---------------------------------------

from skills.cvm.calculations._registry import (  # noqa: E402
    EngineSpec, MetricSpec, register_engine, register_metric,
)
register_engine(EngineSpec(
    name="beta",
    quantity="beta",
    at_fn=beta_at,  # [v4 P0] Returns float|None, matching EngineSpec contract
    periods_fn=beta_periods,
    source="COTAHIST (stock prices) + brapi ^BVSP (IBOV) -> 5Y rolling OLS regression",
    category="market",
))

# [v1.13] Register Beta as a METRIC so resolve_metric("beta") works in the
# historical dashboard's summary() call. Before this, beta was only registered
# as an EngineSpec, so summary(metric="beta") raised ValueError and the
# dashboard silently skipped it (showed no data).
# allow_negative=True: countercyclical stocks can have negative beta.
register_metric(MetricSpec(
    name="beta",
    per_share_label=None, per_share_key=None, per_share_fn=None,
    ratio_label="Beta (5A)",
    ratio_key="beta",
    ratio_fn=beta_at,
    history_fn=beta_periods,
    engines=["beta"],
    category="market",
    aliases=["beta_5y", "market_beta"],
    allow_negative=True,
    tooltip="Beta = Cov(Retorno ação, Retorno IBOV) / Var(IBOV). Sensibilidade ao mercado. >1 mais volátil, <1 menos volátil, <0 anticíclico.",
))
