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


# [v2.0 fix] Module-level IBOV cache + brapi skip flag.
# IBOV 5Y history doesn't change during a single dashboard run, so we
# fetch it ONCE per process and reuse. Without this, each metric that
# depends on beta (coe, wacc, dupont via coe, altman_z via price) would
# trigger a separate brapi ^BVSP fetch, causing 100+ HTTP requests + 20+
# minutes of runtime. Now: 1 fetch (or 1 failure + skip), then cache.
_IBOV_CACHE: dict[str, dict] = {}  # key: f"{end_date}:{years}" -> returns dict
_IBOV_BRAPI_FAILED = False  # set True after first brapi failure, skip subsequent


def _fetch_stock_returns(ticker: str, end_date: str, years: int = 5) -> dict[str, float]:
    """Fetch daily returns for a stock from COTAHIST.

    [v1.14] NOT @engine_cached because the outer beta_at/beta_stats_at/beta_periods
    ARE cached, so this is only called on cache miss. Adding @engine_cached here
    would create redundant cache entries for the same (ticker, end_date) key.
    """
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
    """Fetch daily returns for IBOV. Tries brapi ^BVSP, falls back to COTAHIST proxy.

    [v2.0 fix] Module-level cache (_IBOV_CACHE) so IBOV 5Y history is
    fetched ONCE per process. Without this, each metric depending on beta
    (coe, wacc, dupont, altman_z) would trigger a separate brapi fetch,
    causing 100+ HTTP requests + 20+ minutes. Also has a skip flag
    (_IBOV_BRAPI_FAILED) so after the first brapi failure, subsequent
    calls go straight to the COTAHIST proxy without retrying brapi.
    """
    global _IBOV_BRAPI_FAILED

    cache_key = f"{end_date}:{years}"
    if cache_key in _IBOV_CACHE:
        return _IBOV_CACHE[cache_key]

    # Path 1: Try brapi ^BVSP (skip if previously failed)
    if not _IBOV_BRAPI_FAILED:
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
                        _IBOV_CACHE[cache_key] = returns
                        return returns
            else:
                # brapi returned error/not_found — set skip flag
                _IBOV_BRAPI_FAILED = True
        except Exception:
            _IBOV_BRAPI_FAILED = True

    # Path 2: Fallback via COTAHIST proxy
    returns = _fetch_ibov_proxy_from_cotahist(end_date, years)
    if returns:
        _IBOV_CACHE[cache_key] = returns
    return returns


def _get_top_ibov_constituents() -> list[tuple[str, float]]:
    """Get top IBOV constituents (ticker + weight) from B3 index DB.

    [v4 P2] Queries data_sources.b3.index dynamically instead of hardcoding.
    Falls back to a hardcoded list if the index DB is not synced.

    [new commit] Now returns (ticker, participation) tuples so the proxy
    can compute a market-cap-weighted average (was unweighted — IBOV is
    free-float market-cap weighted, so equal weighting distorted the proxy
    when low-weight constituents like MGLU3 moved while high-weight ones
    like PETR4 stayed flat). Found by external LLM review (Qwen).
    """
    try:
        from data_sources.b3.index.catalog import connect as index_connect
        from data_sources.b3.index.catalog import db_path as index_db_path
        path = index_db_path()
        if path.exists():
            conn = index_connect(read_only=True)
            rows = conn.execute(
                """SELECT ticker, participation FROM index_constituents
                   WHERE index_code = 'IBOV'
                     AND ref_date = (SELECT MAX(ref_date) FROM index_constituents WHERE index_code = 'IBOV')
                   ORDER BY participation DESC LIMIT 10"""
            ).fetchall()
            conn.close()
            if rows:
                return [(r["ticker"], float(r["participation"] or 0)) for r in rows]
    except Exception:
        pass

    # Fallback: hardcoded top 10 with approximate weights (as of 2024-Q4).
    # Weights sum to ~0.65 (top 10 cover ~65% of IBOV). If weights are 0 the
    # proxy falls back to equal weighting (graceful degradation).
    return [("PETR4", 0.12), ("VALE3", 0.11), ("ITUB4", 0.10), ("BBDC4", 0.08),
            ("BBAS3", 0.07), ("ABEV3", 0.06), ("B3SA3", 0.05), ("MGLU3", 0.04),
            ("RENT3", 0.03), ("WEGE3", 0.03)]


def _fetch_ibov_proxy_from_cotahist(end_date: str, years: int = 5) -> dict[str, float]:
    """Compute IBOV proxy returns from top constituents via COTAHIST.

    [new commit] Now uses market-cap-weighted average (was equal-weighted).
    IBOV is a free-float market-cap-weighted index; equal weighting distorted
    the proxy. Uses the `participation` column from the B3 index DB.
    """
    from skills.cvm.calculations.engines.price import price_series

    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")
    constituents = _get_top_ibov_constituents()

    all_series: dict[str, dict[str, float]] = {}
    weights: dict[str, float] = {}
    total_weight = 0.0
    for ticker, weight in constituents:
        prices = price_series(ticker, start_date, end_date)
        if len(prices) >= 60:
            all_series[ticker] = {p["date"]: p["close"] for p in prices}
            weights[ticker] = weight
            total_weight += weight

    if len(all_series) < 5:
        return {}

    # Normalize weights to sum to 1.0 (in case some constituents were skipped)
    if total_weight > 0:
        for t in weights:
            weights[t] /= total_weight
    else:
        # All weights were 0 — fall back to equal weighting
        eq = 1.0 / len(all_series)
        for t in all_series:
            weights[t] = eq

    all_dates = set()
    for series in all_series.values():
        all_dates.update(series.keys())
    all_dates = sorted(all_dates)

    returns = {}
    prev_avg = None
    for date in all_dates:
        # [new commit] Weighted average (was equal-weighted sum/len).
        # Only include constituents that have a price on this date.
        weighted_sum = 0.0
        weight_sum = 0.0
        for ticker, series in all_series.items():
            if date in series:
                w = weights.get(ticker, 0)
                weighted_sum += series[date] * w
                weight_sum += w
        if weight_sum < 0.01:  # need at least some weight coverage
            continue
        avg_close = weighted_sum / weight_sum
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
def beta_periods(company: str, date_from: str | None = None,
                 date_to: str | None = None) -> list[dict]:
    """Get all Beta periods for a company (monthly sampling).

    [v1.14] SIGNATURE FIX: Now accepts (company, date_from, date_to) to match
    the MetricSpec history_fn contract. Was (company) only — caused TypeError
    in summary() which calls history_fn(company, date_from, date_to), making
    Beta show "—" in the dashboard.

    [v1.14] WINDOW FIX: Rolling window is now 5Y (1260 trading days) to match
    the "Beta (5A)" label. Was 1Y (252 days) — inconsistent with beta_at()
    which uses a 5Y window.

    [v4 P0] PERFORMANCE: Fetches stock + IBOV prices ONCE, then computes
    rolling windows in-memory. Was 660+ DB round-trips, now 2.

    Returns list of {"date": ..., "beta": float, "r_squared": float} sorted oldest-first.
    """
    # [v4 P1] Use timedelta, not .replace(year=...), to avoid Feb 29 crash
    # [new commit] Respect date_to if provided (was hardcoded datetime.now()).
    # This makes beta_periods deterministic + testable + reproducible.
    if date_to:
        end_date = date_to
    else:
        end_date = datetime.now().strftime("%Y-%m-%d")
    # Fetch 6Y of data so the earliest monthly checkpoint has enough history
    # for a 5Y rolling window (need 5Y of data BEFORE the checkpoint).
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_date = (end_dt - timedelta(days=6 * 365 + 30)).strftime("%Y-%m-%d")

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

    # For each monthly checkpoint, compute rolling 5Y beta from pre-fetched data
    # [v1.14] Changed from 1Y (252) to 5Y (1260) to match the "Beta (5A)" label.
    periods = []
    min_window = 60  # minimum data points for a valid regression
    rolling_window = 252 * 5  # 5Y of trading days

    for idx in monthly_indices:
        checkpoint_date = common_dates[idx]

        # Find the start index for the 5Y window
        window_start = max(0, idx - rolling_window)
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

    # [v1.14] Filter by date_from / date_to if provided (MetricSpec history_fn contract)
    if date_from:
        periods = [p for p in periods if p["date"] >= date_from]
    if date_to:
        periods = [p for p in periods if p["date"] <= date_to]

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
