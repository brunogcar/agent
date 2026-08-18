"""skills/b3/price/engines.py -- OHLCV + technical analysis engines.

Queries cotahist.db for daily OHLCV data and computes technical indicators:
  - Moving averages (SMA20/50/100/200, EMA for MACD)
  - Volume + volume MA
  - Returns (daily, cumulative, drawdown)
  - Volatility (rolling 20D/60D/252D)
  - Bollinger Bands (20, 2σ)
  - Momentum oscillators (RSI, MACD, Stochastic, OBV)  [v1.2]
  - Dividend-adjusted close (backward adjustment)      [v1.3]
  - Fibonacci levels + trade setup                     [v1.3]

Usage:
    from skills.b3.price.engines import ohlcv_series, compute_sma, compute_returns
    s = ohlcv_series("PETR4", "2024-01-01", "2024-12-31")
    ma20 = compute_sma([p["close"] for p in s], 20)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _cotahist_db() -> Path:
    """Return path to cotahist.db."""
    try:
        from data_sources.cvm._db import cvm_db_path
        return cvm_db_path().parent / "b3" / "cotahist.db"
    except Exception:
        return Path.cwd() / "memory_db" / "b3" / "cotahist.db"


def _connect() -> sqlite3.Connection:
    path = _cotahist_db()
    if not path.exists():
        raise FileNotFoundError(f"cotahist.db not found at {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ohlcv_series(ticker: str, date_from: str, date_to: str) -> list[dict]:
    """Get daily OHLCV data for a ticker.

    Returns: [{"date", "open", "high", "low", "close", "volume", "trade_count", "contracts"}]
    sorted oldest-first.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            """SELECT refdate, open, high, low, close, volume, trade_count, contracts,
                      best_bid, best_ask
               FROM cotahist
               WHERE symbol = ? AND refdate >= ? AND refdate <= ?
               AND market_type = 10 AND close IS NOT NULL AND close > 0
               ORDER BY refdate ASC""",
            (ticker.strip().upper(), date_from, date_to),
        ).fetchall()
        conn.close()
        return [
            {
                "date": r["refdate"],
                "open": float(r["open"]) if r["open"] else None,
                "high": float(r["high"]) if r["high"] else None,
                "low": float(r["low"]) if r["low"] else None,
                "close": float(r["close"]),
                "volume": float(r["volume"]) if r["volume"] else 0.0,
                "trade_count": int(r["trade_count"]) if r["trade_count"] else 0,
                "contracts": int(r["contracts"]) if r["contracts"] else 0,
                "best_bid": float(r["best_bid"]) if r["best_bid"] else None,
                "best_ask": float(r["best_ask"]) if r["best_ask"] else None,
            }
            for r in rows
        ]
    except Exception:
        return []


def latest_quote(ticker: str) -> dict | None:
    """Get the latest available quote for a ticker."""
    try:
        conn = _connect()
        row = conn.execute(
            """SELECT refdate, open, high, low, close, volume, trade_count
               FROM cotahist
               WHERE symbol = ? AND market_type = 10 AND close IS NOT NULL AND close > 0
               ORDER BY refdate DESC LIMIT 1""",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "date": row["refdate"],
            "open": float(row["open"]) if row["open"] else None,
            "high": float(row["high"]) if row["high"] else None,
            "low": float(row["low"]) if row["low"] else None,
            "close": float(row["close"]),
            "volume": float(row["volume"]) if row["volume"] else 0.0,
            "trade_count": int(row["trade_count"]) if row["trade_count"] else 0,
        }
    except Exception:
        return None


def compute_sma(closes: list[float | None], period: int) -> list[float | None]:
    """Compute Simple Moving Average for a list of close prices.

    Returns a list of the same length. First (period-1) entries are None.
    """
    result: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
            continue
        window = [c for c in closes[i - period + 1 : i + 1] if c is not None]
        if len(window) == period:
            result.append(sum(window) / period)
        else:
            result.append(None)
    return result


def compute_returns(closes: list[float | None]) -> list[float | None]:
    """Compute daily returns: (close[i] - close[i-1]) / close[i-1]."""
    result: list[float | None] = [None]
    for i in range(1, len(closes)):
        if closes[i] is not None and closes[i - 1] is not None and closes[i - 1] != 0:
            result.append((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            result.append(None)
    return result


def compute_cumulative_returns(closes: list[float | None]) -> list[float | None]:
    """Compute cumulative return from the first valid close."""
    first_valid = None
    for c in closes:
        if c is not None and c > 0:
            first_valid = c
            break
    if first_valid is None:
        return [None] * len(closes)
    return [(c / first_valid - 1.0) if c is not None and c > 0 else None for c in closes]


def compute_drawdowns(closes: list[float | None]) -> list[float | None]:
    """Compute drawdown from running peak. Returns negative fractions (or 0)."""
    result: list[float | None] = []
    peak: float | None = None
    for c in closes:
        if c is None:
            result.append(None)
            continue
        if peak is None or c > peak:
            peak = c
        if peak > 0:
            result.append(c / peak - 1.0)
        else:
            result.append(None)
    return result


def compute_volatility(returns: list[float | None], period: int) -> list[float | None]:
    """Compute rolling annualized volatility (period-day, ×√252)."""
    import math
    result: list[float | None] = []
    for i in range(len(returns)):
        if i < period:
            result.append(None)
            continue
        window = [r for r in returns[i - period : i] if r is not None]
        if len(window) < period // 2:
            result.append(None)
            continue
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / len(window)
        result.append(math.sqrt(var) * math.sqrt(252))
    return result


def compute_bollinger_bands(
    closes: list[float | None], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Compute Bollinger Bands. Returns (upper, middle, lower)."""
    import math
    upper: list[float | None] = []
    middle: list[float | None] = []
    lower: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            middle.append(None)
            lower.append(None)
            continue
        window = [c for c in closes[i - period + 1 : i + 1] if c is not None]
        if len(window) < period:
            upper.append(None)
            middle.append(None)
            lower.append(None)
            continue
        mean = sum(window) / period
        var = sum((c - mean) ** 2 for c in window) / period
        std = math.sqrt(var)
        middle.append(mean)
        upper.append(mean + num_std * std)
        lower.append(mean - num_std * std)
    return upper, middle, lower


def find_ma_crossovers(
    dates: list[str], ma_fast: list[float | None], ma_slow: list[float | None],
    fast_label: str = "MA20", slow_label: str = "MA50",
) -> list[dict]:
    """Find crossover points where fast MA crosses slow MA.

    Returns list of {"date", "type": "golden"|"death", "fast": val, "slow": val}.
    """
    crossovers: list[dict] = []
    prev_diff: float | None = None
    for i in range(len(dates)):
        if ma_fast[i] is None or ma_slow[i] is None:
            continue
        diff = ma_fast[i] - ma_slow[i]
        if prev_diff is not None:
            if prev_diff < 0 and diff >= 0:
                crossovers.append({
                    "date": dates[i], "type": "golden",
                    "signal": "Compra (Cruzamento de Ouro)",
                    "fast_label": fast_label, "slow_label": slow_label,
                    "fast": ma_fast[i], "slow": ma_slow[i],
                })
            elif prev_diff > 0 and diff <= 0:
                crossovers.append({
                    "date": dates[i], "type": "death",
                    "signal": "Venda (Cruzamento de Morte)",
                    "fast_label": fast_label, "slow_label": slow_label,
                    "fast": ma_fast[i], "slow": ma_slow[i],
                })
        prev_diff = diff
    return crossovers


def compute_52w_range(ticker: str, today: str) -> dict:
    """Compute 52-week high/low for a ticker."""
    from datetime import date as _date, timedelta as _timedelta
    try:
        d = _date.fromisoformat(today)
        date_from = (d - _timedelta(days=365)).isoformat()
        conn = _connect()
        row = conn.execute(
            """SELECT MAX(high) as high_52w, MIN(low) as low_52w,
                      MAX(close) as close_high, MIN(close) as close_low
               FROM cotahist
               WHERE symbol = ? AND refdate >= ? AND refdate <= ?
               AND market_type = 10 AND close > 0""",
            (ticker.strip().upper(), date_from, today),
        ).fetchone()
        conn.close()
        if not row or row["high_52w"] is None:
            return {"high_52w": None, "low_52w": None}
        return {
            "high_52w": float(row["high_52w"]),
            "low_52w": float(row["low_52w"]),
        }
    except Exception:
        return {"high_52w": None, "low_52w": None}


# ── Momentum oscillators (v1.2) ──────────────────────────────────────────────


def compute_ema(closes: list[float | None], period: int) -> list[float | None]:
    """[v1.2] Compute Exponential Moving Average.

    Standard convention: seed with the SMA of the first ``period`` valid
    closes, then apply the EMA recursion from there. The multiplier is
    ``2 / (period + 1)``.

    Returns a list of the same length. First ``period - 1`` entries are
    None (warmup). Used as the building block for MACD.
    """
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period:
        return result
    # Seed: SMA of the first `period` closes (must all be non-None).
    seed_window = closes[:period]
    if any(c is None for c in seed_window):
        # Fall back: find the first window of `period` consecutive non-None values.
        return _ema_with_gaps(closes, period)
    ema_prev: float | None = sum(seed_window) / period  # type: ignore[arg-type]
    result[period - 1] = ema_prev
    mult = 2.0 / (period + 1)
    for i in range(period, n):
        c = closes[i]
        if c is None or ema_prev is None:
            result[i] = result[i - 1]  # carry forward (don't break the line)
            continue
        ema_prev = c * mult + ema_prev * (1.0 - mult)
        result[i] = ema_prev
    return result


def _ema_with_gaps(closes: list[float | None], period: int) -> list[float | None]:
    """EMA when the input has None gaps — finds the first window of `period`
    consecutive non-None values to seed, then recurses."""
    n = len(closes)
    result: list[float | None] = [None] * n
    seed_start = None
    for i in range(n - period + 1):
        window = closes[i : i + period]
        if all(c is not None for c in window):
            seed_start = i
            break
    if seed_start is None:
        return result
    ema_prev: float = sum(closes[seed_start : seed_start + period]) / period  # type: ignore[arg-type]
    result[seed_start + period - 1] = ema_prev
    mult = 2.0 / (period + 1)
    for i in range(seed_start + period, n):
        c = closes[i]
        if c is None:
            result[i] = result[i - 1]
            continue
        ema_prev = c * mult + ema_prev * (1.0 - mult)
        result[i] = ema_prev
    return result


def compute_rsi(closes: list[float | None], period: int = 14) -> list[float | None]:
    """[v1.2] Compute Relative Strength Index (Wilder's smoothing).

    Standard 14-day RSI. Uses Wilder's smoothing (not a plain SMA) for the
    average gain/loss recursion: ``avg[t] = (avg[t-1] * (period-1) + val[t]) / period``.

    Returns a list of the same length. First ``period`` entries are None
    (warmup — needs `period` daily changes to seed). Values are 0-100.
    RSI = 100 when avg_loss = 0 (all gains); RSI = 0 when avg_gain = 0.
    """
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result

    # Daily changes (None where either side is None → 0.0 gain/loss).
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        prev, cur = closes[i - 1], closes[i]
        if prev is None or cur is None:
            continue
        change = cur - prev
        gains[i] = max(0.0, change)
        losses[i] = max(0.0, -change)

    # Seed: SMA of first `period` gains/losses (indices 1..period).
    seed_gains = gains[1 : period + 1]
    seed_losses = losses[1 : period + 1]
    avg_gain = sum(seed_gains) / period
    avg_loss = sum(seed_losses) / period
    result[period] = _rsi_from_avg(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i] = _rsi_from_avg(avg_gain, avg_loss)
    return result


def _rsi_from_avg(avg_gain: float, avg_loss: float) -> float:
    """RSI = 100 - 100/(1+RS) where RS = avg_gain/avg_loss."""
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_macd(
    closes: list[float | None],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """[v1.2] Compute MACD (Moving Average Convergence Divergence).

    Returns a 3-tuple of lists (same length as ``closes``):
      - ``macd_line``   = EMA(fast) - EMA(slow). None for first ``slow-1`` entries.
      - ``signal_line`` = EMA(macd_line, signal). None until ``slow - 1 + signal - 1``.
      - ``histogram``   = macd_line - signal_line. None where either is None.

    Standard parameters: fast=12, slow=26, signal=9.
    """
    ema_fast = compute_ema(closes, fast)
    ema_slow = compute_ema(closes, slow)

    n = len(closes)
    macd_line: list[float | None] = [None] * n
    for i in range(n):
        f, s = ema_fast[i], ema_slow[i]
        if f is not None and s is not None:
            macd_line[i] = f - s

    # Signal line = EMA of the macd_line (over the valid region only).
    signal_line: list[float | None] = [None] * n
    first_valid = None
    for i in range(n):
        if macd_line[i] is not None:
            first_valid = i
            break
    if first_valid is not None:
        valid_macd = [macd_line[i] for i in range(first_valid, n)]  # type: ignore[list-item]
        valid_signal = compute_ema(valid_macd, signal)
        for i, v in enumerate(valid_signal):
            signal_line[first_valid + i] = v

    # Histogram = macd - signal (None where either is None).
    histogram: list[float | None] = [None] * n
    for i in range(n):
        m, s = macd_line[i], signal_line[i]
        if m is not None and s is not None:
            histogram[i] = m - s

    return macd_line, signal_line, histogram


def compute_stochastic(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """[v1.2] Compute Stochastic Oscillator (14/3/3).

    Returns a 2-tuple of lists (same length as input):
      - ``k_line`` = %K = (close - lowest_low) / (highest_high - lowest_low) * 100.
        None for first ``k_period - 1`` entries.
      - ``d_line`` = %D = SMA of %K over ``d_period``. None for first
        ``k_period - 1 + d_period - 1`` entries.

    When highest_high == lowest_low (flat period), %K is set to 50 (neutral)
    to avoid division by zero.
    """
    n = len(closes)
    k_line: list[float | None] = [None] * n
    if n < k_period:
        return k_line, [None] * n

    for i in range(k_period - 1, n):
        window_h = [h for h in highs[i - k_period + 1 : i + 1] if h is not None]
        window_l = [l for l in lows[i - k_period + 1 : i + 1] if l is not None]
        if len(window_h) < k_period or len(window_l) < k_period:
            continue
        hh = max(window_h)
        ll = min(window_l)
        c = closes[i]
        if c is None:
            continue
        if hh == ll:
            k_line[i] = 50.0  # neutral (no range)
        else:
            k_line[i] = (c - ll) / (hh - ll) * 100.0

    # %D = SMA of %K over d_period.
    d_line: list[float | None] = [None] * n
    for i in range(k_period - 1 + d_period - 1, n):
        window = [k_line[i - d_period + 1 + j] for j in range(d_period)]
        if any(v is None for v in window):
            continue
        d_line[i] = sum(window) / d_period  # type: ignore[arg-type]

    return k_line, d_line


def compute_obv(
    closes: list[float | None],
    volumes: list[float | None],
) -> list[float | None]:
    """[v1.2] Compute On-Balance Volume (cumulative signed volume).

    OBV[t] = OBV[t-1] + volume[t]  if close[t] > close[t-1]
    OBV[t] = OBV[t-1] - volume[t]  if close[t] < close[t-1]
    OBV[t] = OBV[t-1]              if close[t] == close[t-1] (or either is None)

    Returns a list of the same length. OBV[0] = 0.0 (no prior day to compare).
    None values are carried forward (OBV stays flat when close or volume is None).
    """
    n = len(closes)
    result: list[float | None] = [0.0] * n
    if n == 0:
        return result
    obv = 0.0
    result[0] = obv
    for i in range(1, n):
        prev, cur = closes[i - 1], closes[i]
        vol = volumes[i] if i < len(volumes) else None
        if prev is None or cur is None or vol is None:
            result[i] = obv  # flat
            continue
        if cur > prev:
            obv += vol
        elif cur < prev:
            obv -= vol
        result[i] = obv
    return result


# ── Trend / cyclical indicators (v1.6) -- ADX, CCI, Williams %R ────────────


def compute_adx(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    period: int = 14,
) -> list[float | None]:
    """[v1.6] Compute Average Directional Index (Wilder smoothing).

    ADX measures TREND STRENGTH (not direction): 0-100. ADX > 25 = strong
    trend (bull or bear); ADX < 20 = weak/no trend. Complements MACD.

    Steps:
      1. True Range (TR) = max(high-low, |high-prev_close|, |low-prev_close|)
      2. +DM = high[t]-high[t-1] if > 0 AND > (low[t-1]-low[t]) else 0
         -DM = low[t-1]-low[t]  if > 0 AND > (high[t]-high[t-1]) else 0
      3. Wilder smoothing of TR, +DM, -DM (same recursion as RSI):
         avg[t] = (avg[t-1] * (period-1) + val[t]) / period
      4. +DI = 100 * smoothed(+DM) / smoothed(TR)
         -DI = 100 * smoothed(-DM) / smoothed(TR)
      5. DX = |+DI - -DI| / (+DI + -DI) * 100
      6. ADX = SMA(DX, period) -- the user task spec says SMA, not Wilder

    Returns a list of the same length. First ``2*period`` entries are
    None (warmup -- needs ``period`` TRs to seed + ``period`` DXs to
    smooth). Values are 0-100.
    """
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < 2 * period + 1:
        return result

    # Step 1-2: TR + +DM + -DM arrays (length n; index 0 has no prev).
    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        h, l, c = highs[i], lows[i], closes[i]
        ph, pl = highs[i-1], lows[i-1]
        pc = closes[i-1]
        if h is None or l is None or c is None or ph is None or pl is None or pc is None:
            continue
        # True Range.
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        # Directional movement.
        up = h - ph
        down = pl - l
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    # Step 3: Wilder smoothing of TR, +DM, -DM (seed = sum of first `period`).
    atr = [0.0] * n
    s_plus_dm = [0.0] * n
    s_minus_dm = [0.0] * n
    # Seed at index `period` (uses indices 1..period).
    atr[period] = sum(tr[1:period+1])
    s_plus_dm[period] = sum(plus_dm[1:period+1])
    s_minus_dm[period] = sum(minus_dm[1:period+1])
    for i in range(period + 1, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        s_plus_dm[i] = (s_plus_dm[i-1] * (period - 1) + plus_dm[i]) / period
        s_minus_dm[i] = (s_minus_dm[i-1] * (period - 1) + minus_dm[i]) / period

    # Step 4-5: +DI, -DI, DX (compute from index `period` onward).
    dx = [None] * n
    for i in range(period, n):
        if atr[i] <= 0:
            continue
        plus_di = 100.0 * s_plus_dm[i] / atr[i]
        minus_di = 100.0 * s_minus_dm[i] / atr[i]
        denom = plus_di + minus_di
        if denom <= 0:
            dx[i] = 0.0
        else:
            dx[i] = abs(plus_di - minus_di) / denom * 100.0

    # Step 6: ADX = SMA of DX over `period` (per user spec).
    # First valid DX is at index `period`; ADX first valid at 2*period - 1.
    for i in range(2 * period - 1, n):
        window = dx[i - period + 1: i + 1]
        if any(v is None for v in window):
            continue
        result[i] = sum(window) / period
    return result


def compute_cci(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    period: int = 20,
) -> list[float | None]:
    """[v1.6] Compute Commodity Channel Index (cyclical oscillator).

    CCI measures deviation of the typical price from its SMA, normalized by
    the mean deviation. CCI > +100 = overbought; CCI < -100 = oversold.

    Formulas:
      typical_price (TP) = (H + L + C) / 3
      SMA_TP        = SMA(TP, period)
      mean_dev      = SMA(|TP - SMA_TP|, period)
      CCI           = (TP - SMA_TP) / (0.015 * mean_dev)

    The 0.015 constant is Lambert\'s original -- it makes ~70-80% of CCI
    values fall in the [-100, +100] range. Returns a list of the same
    length. First ``period - 1`` entries are None (warmup).
    """
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period:
        return result

    # Typical price series.
    tp = [None] * n
    for i in range(n):
        h, l, c = highs[i], lows[i], closes[i]
        if h is None or l is None or c is None:
            continue
        tp[i] = (h + l + c) / 3.0

    for i in range(period - 1, n):
        window = tp[i - period + 1: i + 1]
        if any(v is None for v in window):
            continue
        sma_tp = sum(window) / period
        mean_dev = sum(abs(v - sma_tp) for v in window) / period
        if mean_dev <= 0:
            result[i] = 0.0
        else:
            result[i] = (tp[i] - sma_tp) / (0.015 * mean_dev)
    return result


def compute_williams_r(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    period: int = 14,
) -> list[float | None]:
    """[v1.6] Compute Williams %R (momentum oscillator, 0 to -100).

    %R = (highest_high - close) / (highest_high - lowest_low) * -100

    Uses a rolling window of `period` days for highest_high + lowest_low.
    %R > -20 = overbought; %R < -80 = oversold. Mathematically equivalent
    to inverted %K (Stochastic) but with a different scale + convention.

    Returns a list of the same length. First ``period - 1`` entries are
    None (warmup). Values are 0 to -100 (always non-positive).
    """
    n = len(closes)
    result: list[float | None] = [None] * n
    if n < period:
        return result

    for i in range(period - 1, n):
        window_h = [h for h in highs[i - period + 1: i + 1] if h is not None]
        window_l = [l for l in lows[i - period + 1: i + 1] if l is not None]
        c = closes[i]
        if len(window_h) < period or len(window_l) < period or c is None:
            continue
        hh = max(window_h)
        ll = min(window_l)
        if hh == ll:
            result[i] = -50.0  # neutral (no range)
        else:
            result[i] = (hh - c) / (hh - ll) * -100.0
    return result


# ── Bid-ask spread (v1.6) -- for the new Bid-Ask Spread tab ────────────────


def compute_bid_ask_spread(
    best_bids: list[float | None],
    best_asks: list[float | None],
) -> list[float | None]:
    """[v1.6] Compute the absolute bid-ask spread (best_ask - best_bid).

    Returns a list of the same length. Entries are None where either side
    is missing (NULL in cotahist). Spread is always non-negative (the B3
    feed guarantees ask >= bid for valid quotes).
    """
    n = max(len(best_bids), len(best_asks))
    result: list[float | None] = [None] * n
    for i in range(n):
        b = best_bids[i] if i < len(best_bids) else None
        a = best_asks[i] if i < len(best_asks) else None
        if b is None or a is None:
            continue
        result[i] = a - b
    return result


def compute_spread_pct(
    best_bids: list[float | None],
    best_asks: list[float | None],
    closes: list[float | None] | None = None,
) -> list[float | None]:
    """[v1.6] Compute relative bid-ask spread (% of close).

    spread_pct = (best_ask - best_bid) / close * 100

    Returns a list of the same length. None where either side or the close
    is missing (or close <= 0). Values are non-negative percentages
    (e.g. 0.05 = 5 bps).

    [v1.6-v2] Signature now accepts an optional closes list so the
    spread can be expressed as a fraction of the closing price (matches
    the task spec). When closes is None or shorter than the bid/ask
    arrays, the corresponding entries are None.
    """
    n = max(len(best_bids), len(best_asks))
    result: list[float | None] = [None] * n
    for i in range(n):
        b = best_bids[i] if i < len(best_bids) else None
        a = best_asks[i] if i < len(best_asks) else None
        c = closes[i] if (closes is not None and i < len(closes)) else None
        if b is None or a is None or c is None or c <= 0:
            continue
        result[i] = (a - b) / c * 100.0
    return result


# ── Dividend-adjusted close + Fibonacci (v1.3) ──────────────────────────────


def compute_adjusted_close(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
) -> tuple[list[float | None], list[dict]]:
    """[v1.3] Compute backward dividend-adjusted close prices.

    Standard backward adjustment: for each dividend paid AFTER date t,
    subtract the dividend amount from close[t]. This makes historical
    prices comparable to today's (unadjusted) close. The most recent
    close is NEVER adjusted (it's the reference point).

    Uses ``data_sources.b3.dividends.query_engine.dividends(ticker)`` to
    fetch cash dividends. If the dividends DB is not synced or the query
    fails, gracefully degrades — returns the raw closes + an empty
    adjustments list.

    Args:
        ticker: B3 ticker (PETR4).
        dates:  list of YYYY-MM-DD strings (aligned with closes).
        closes: daily close prices (raw, unadjusted).

    Returns:
        ``(adjusted_closes, adjustments)`` where:
          - ``adjusted_closes`` = same length as closes, backward-adjusted.
          - ``adjustments`` = list of ``{ex_date, rate, payment_date}``
            dicts for each dividend applied (empty if none/failed).
    """
    n = len(closes)
    adjusted = list(closes)  # copy (don't mutate input)
    adjustments: list[dict] = []

    if not ticker or n == 0:
        return adjusted, adjustments

    # [v1.3-v2] Get the ticker's ISIN from cotahist so we can filter
    # dividends by ISIN (not just ticker). The b3_dividends API returns
    # ALL dividends for the issuing company (e.g., both PETR3 + PETR4 when
    # syncing PETR4), so filtering by ticker alone returns mixed dividends.
    # Filtering by ISIN ensures only the correct share class's dividends
    # are applied (PETR4 ISIN = BRPETRACNPR6, PETR3 ISIN = BRPETRACNPR3).
    isin: str | None = None
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT DISTINCT isin FROM cotahist "
            "WHERE symbol = ? AND isin IS NOT NULL AND isin != '' LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()
        if row:
            isin = row["isin"] if isinstance(row, sqlite3.Row) else row[0]
    except Exception:
        pass  # cotahist DB not available — skip ISIN filtering (fall back to ticker-only)

    # Fetch cash dividends from b3_dividends source.
    try:
        from data_sources.b3.dividends.query_engine import dividends as _div_fn
        result = _div_fn(ticker=ticker, limit=200)
        if not isinstance(result, dict) or result.get("status") != "ok":
            return adjusted, adjustments
        divs = result.get("dividends") or []
    except Exception:
        return adjusted, adjustments

    # [v1.3-v2] Filter dividends by ISIN (if we found one). This excludes
    # dividends for the wrong share class (e.g., PETR3 dividends when
    # computing adjusted close for PETR4).
    if isin:
        divs = [d for d in divs if d.get("isin_code") == isin]

    # Build a date → index map for fast lookup.
    date_to_idx = {d: i for i, d in enumerate(dates)}

    for div in divs:
        ex_date = div.get("last_date_prior")  # ex-dividend date
        rate = div.get("rate")
        if not ex_date or rate is None or rate <= 0:
            continue
        payment_date = div.get("payment_date") or ""
        # Find the index of the ex-div date in our series.
        # If the ex-div date is IN the series, adjust all closes BEFORE it.
        # If it's NOT in the series but is after the last date, adjust all.
        # If it's before the first date, skip (can't adjust).
        if ex_date in date_to_idx:
            ex_idx = date_to_idx[ex_date]
        else:
            # Ex-div date not in our series — check if it's after the last date.
            if ex_date > dates[-1]:
                ex_idx = n  # adjust all
            else:
                continue  # before our range — skip

        # Adjust all closes before the ex-div date (backward adjustment).
        for i in range(ex_idx):
            if adjusted[i] is not None:
                adjusted[i] = adjusted[i] - rate

        adjustments.append({
            "ex_date": ex_date,
            "rate": rate,
            "payment_date": payment_date,
            "isin_code": div.get("isin_code") or "",
        })

    return adjusted, adjustments


def find_swing_extremes(
    dates: list[str],
    highs: list[float | None],
    lows: list[float | None],
    lookback_days: int = 90,
) -> dict:
    """[v1.3] Find the most recent swing high + low in a lookback window.

    Args:
        dates:  list of YYYY-MM-DD strings.
        highs:  daily high prices.
        lows:   daily low prices.
        lookback_days: number of calendar days to look back from the latest date.

    Returns:
        ``{high_date, high_price, low_date, low_price, range, lookback_days}``
        where range = high_price - low_price. Returns empty values if
        insufficient data in the lookback window.
    """
    n = len(dates)
    if n == 0:
        return {"high_date": None, "high_price": None,
                "low_date": None, "low_price": None,
                "range": None, "lookback_days": lookback_days}

    from datetime import date as _date, timedelta as _timedelta

    latest = dates[-1]
    try:
        latest_d = _date.fromisoformat(latest)
    except (ValueError, TypeError):
        return {"high_date": None, "high_price": None,
                "low_date": None, "low_price": None,
                "range": None, "lookback_days": lookback_days}

    cutoff = (latest_d - _timedelta(days=lookback_days)).isoformat()

    # Filter to the lookback window.
    high_price = None
    high_date = None
    low_price = None
    low_date = None
    for i in range(n):
        if dates[i] < cutoff:
            continue
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        if h is not None and (high_price is None or h > high_price):
            high_price = h
            high_date = dates[i]
        if l is not None and (low_price is None or l < low_price):
            low_price = l
            low_date = dates[i]

    range_val = None
    if high_price is not None and low_price is not None:
        range_val = high_price - low_price

    return {
        "high_date": high_date,
        "high_price": high_price,
        "low_date": low_date,
        "low_price": low_price,
        "range": range_val,
        "lookback_days": lookback_days,
    }


# Standard Fibonacci levels used in the trade setup.
FIB_LEVELS = [0.236, 0.309, 0.382, 0.500, 0.618, 0.786, 1.000,
               1.618, 2.618, 3.618, 4.236]

# Key levels for entries + targets (user defaults).
ENTRY_1_LEVEL = 0.382
ENTRY_2_LEVEL = 0.618
STOP_BUFFER = 0.10  # 10% of range beyond Entrada 2


def compute_fibonacci_levels(
    swing_high: float,
    swing_low: float,
    levels: list[float] | None = None,
) -> dict[float, float]:
    """[v1.3] Compute Fibonacci retracement prices for a swing.

    For each level L, the retracement price = swing_high - (range × L).
    Level 0.0 = swing_high (no retracement), level 1.0 = swing_low (full retracement).
    Levels > 1.0 are extensions below the swing low.

    Args:
        swing_high: swing high price.
        swing_low:  swing low price.
        levels:     list of Fibonacci ratios (defaults to FIB_LEVELS).

    Returns:
        ``{level: price}`` dict.
    """
    if levels is None:
        levels = FIB_LEVELS
    range_val = swing_high - swing_low
    return {L: swing_high - (range_val * L) for L in levels}


def compute_fibonacci_trade_setup(
    swing_high: float,
    swing_low: float,
) -> dict:
    """[v1.3] Compute the Fibonacci trade setup (COMPRA + VENDA).

    Formulas (verified against the user's spreadsheet):
      COMPRA (buy on pullback from swing high):
        Entrada 1 = High - range × 0.382
        Entrada 2 = High - range × 0.618
        Alvo 1    = High + range × 0.382  (extension above)
        Alvo 2    = High + range × 0.618  (extension above)
        STOP      = Entrada 2 - range × 0.10

      VENDA (sell on rally from swing low):
        Entrada 1 = Low + range × 0.382
        Entrada 2 = Low + range × 0.618
        Alvo 1    = Low - range × 0.382  (extension below)
        Alvo 2    = Low - range × 0.618  (extension below)
        STOP      = Entrada 2 + range × 0.10

    Args:
        swing_high: swing high price.
        swing_low:  swing low price.

    Returns:
        Dict with ``range``, ``compra`` (Entrada1/2, Alvo1/2, Stop),
        ``venda`` (same), and ``fib_levels`` (all levels + prices).
    """
    range_val = swing_high - swing_low

    fib_levels = compute_fibonacci_levels(swing_high, swing_low)

    compra = {
        "entrada_1": swing_high - range_val * ENTRY_1_LEVEL,
        "entrada_2": swing_high - range_val * ENTRY_2_LEVEL,
        "alvo_1":    swing_high + range_val * ENTRY_1_LEVEL,
        "alvo_2":    swing_high + range_val * ENTRY_2_LEVEL,
        "stop":      swing_high - range_val * ENTRY_2_LEVEL - range_val * STOP_BUFFER,
    }

    venda = {
        "entrada_1": swing_low + range_val * ENTRY_1_LEVEL,
        "entrada_2": swing_low + range_val * ENTRY_2_LEVEL,
        "alvo_1":    swing_low - range_val * ENTRY_1_LEVEL,
        "alvo_2":    swing_low - range_val * ENTRY_2_LEVEL,
        "stop":      swing_low + range_val * ENTRY_2_LEVEL + range_val * STOP_BUFFER,
    }

    return {
        "range": range_val,
        "fib_levels": fib_levels,
        "compra": compra,
        "venda": venda,
    }


# ── Cotação tab enhancements (v1.4) ─────────────────────────────────────────


def compute_price_snapshot(
    ohlcv: list[dict],
    range_52w: dict | None,
) -> dict:
    """[v1.4] Compute a price snapshot table row (mirrors the user's spreadsheet row 5).

    Returns prior close, open, current, daily variation (abs + %), intraday
    min/max, 52-week range + position within it.

    Args:
        ohlcv: list of {date, open, high, low, close, volume} (newest-last).
        range_52w: compute_52w_range result {high_52w, low_52w} or None.

    Returns:
        Dict with all snapshot fields (None when data insufficient).
    """
    if not ohlcv or len(ohlcv) < 2:
        return {
            "prior_close": None, "open": None, "current": None,
            "daily_diff": None, "daily_pct": None,
            "intraday_low": None, "intraday_high": None,
            "intraday_range": None, "intraday_range_pct": None,
            "high_52w": None, "low_52w": None,
            "from_52w_low": None, "from_52w_low_pct": None,
            "to_52w_high": None, "to_52w_high_pct": None,
        }
    latest = ohlcv[-1]
    prior_close = ohlcv[-2].get("close")
    current = latest.get("close")
    open_ = latest.get("open")
    low = latest.get("low")
    high = latest.get("high")
    daily_diff = (current - prior_close) if (current is not None and prior_close is not None) else None
    daily_pct = (daily_diff / prior_close) if (daily_diff is not None and prior_close) else None
    intraday_range = (high - low) if (high is not None and low is not None) else None
    intraday_range_pct = (intraday_range / low) if (intraday_range is not None and low) else None
    high_52w = (range_52w or {}).get("high_52w")
    low_52w = (range_52w or {}).get("low_52w")
    from_52w_low = (current - low_52w) if (current is not None and low_52w is not None) else None
    from_52w_low_pct = (from_52w_low / low_52w) if (from_52w_low is not None and low_52w) else None
    to_52w_high = (high_52w - current) if (high_52w is not None and current is not None) else None
    to_52w_high_pct = (to_52w_high / current) if (to_52w_high is not None and current) else None
    return {
        "prior_close": prior_close, "open": open_, "current": current,
        "daily_diff": daily_diff, "daily_pct": daily_pct,
        "intraday_low": low, "intraday_high": high,
        "intraday_range": intraday_range, "intraday_range_pct": intraday_range_pct,
        "high_52w": high_52w, "low_52w": low_52w,
        "from_52w_low": from_52w_low, "from_52w_low_pct": from_52w_low_pct,
        "to_52w_high": to_52w_high, "to_52w_high_pct": to_52w_high_pct,
    }


# Multi-period lookback windows (calendar days).
_PERIOD_LOOKBACKS = [
    {"label": "Dia",        "days": 1},
    {"label": "Semana",     "days": 7},
    {"label": "Mês",        "days": 30},
    {"label": "Trimestre",  "days": 90},
    {"label": "Ano",        "days": 365},
    {"label": "2 anos",     "days": 730},
    {"label": "5 anos",     "days": 1825},
    {"label": "10 anos",    "days": 3650},
    {"label": "15 anos",    "days": 5475},
    {"label": "20 anos",    "days": 7300},
]


def compute_period_returns(dates: list[str], closes: list[float | None]) -> list[dict]:
    """[v1.4] Compute multi-period returns (Dia / Semana / Mês / ... / 20 anos).

    For each lookback window, finds the most recent close N calendar days
    before the latest close + computes the % return + the reference price.

    Args:
        dates:  list of YYYY-MM-DD strings (newest-last).
        closes: daily close prices aligned with dates.

    Returns:
        List of ``{label, days, return_pct, reference_price}`` dicts.
    """
    from datetime import date as _date, timedelta as _timedelta

    if not dates or not closes:
        return []

    latest_date = dates[-1]
    try:
        latest_d = _date.fromisoformat(latest_date)
    except (ValueError, TypeError):
        return []

    latest_close = closes[-1]
    if latest_close is None:
        return []

    results: list[dict] = []
    for p in _PERIOD_LOOKBACKS:
        cutoff = (latest_d - _timedelta(days=p["days"])).isoformat()
        # Find the most recent close on or before the cutoff date.
        ref_close = None
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= cutoff:
                if closes[i] is not None:
                    ref_close = closes[i]
                    break
        if ref_close is not None and ref_close != 0:
            ret = (latest_close - ref_close) / ref_close
        else:
            ret = None
        results.append({
            "label": p["label"],
            "days": p["days"],
            "return_pct": ret,
            "reference_price": ref_close,
        })
    return results


def compute_annual_returns(dates: list[str], closes: list[float | None]) -> list[dict]:
    """[v1.4] Compute per-year Início + Fim prices + % return.

    Groups the daily closes by calendar year. For each year:
      - Início = first non-None close of the year
      - Fim = last non-None close of the year
      - % = (Fim - Início) / Início

    Returns the list oldest-first. The current (incomplete) year is included
    with Fim = latest close (not end-of-year).

    Args:
        dates:  list of YYYY-MM-DD strings.
        closes: daily close prices.

    Returns:
        List of ``{year, inicio, fim, return_pct}`` dicts.
    """
    if not dates:
        return []

    by_year: dict[int, list[float]] = {}
    for d, c in zip(dates, closes):
        try:
            y = int(d[:4])
        except (ValueError, IndexError):
            continue
        if c is None:
            continue
        by_year.setdefault(y, []).append(c)

    results: list[dict] = []
    for y in sorted(by_year.keys()):
        prices = by_year[y]
        inicio = prices[0]
        fim = prices[-1]
        ret = (fim - inicio) / inicio if inicio else None
        results.append({
            "year": y,
            "inicio": inicio,
            "fim": fim,
            "return_pct": ret,
        })
    return results


def compute_price_histogram(closes: list[float | None], n_bins: int = 30) -> dict:
    """[v1.4] Compute a price histogram (distribution of daily closes).

    Bins all valid closes into ``n_bins`` equal-width bins between min + max.
    Returns bin labels + counts + a heatmap color per bar (blue→yellow→red
    based on count relative to max).

    Also identifies the Point of Control (highest bin) + the Value Area
    (the contiguous bins around the POC containing ~70% of the data).

    Args:
        closes: daily close prices.
        n_bins: number of bins (default 30).

    Returns:
        ``{bins: [{label, low, high, count, color}], max_count, poc_label,
        value_area_low, value_area_high, total_days}`` or empty dict if
        insufficient data.
    """
    valid = [c for c in closes if c is not None and c > 0]
    if len(valid) < 2:
        return {"bins": [], "max_count": 0, "poc_label": None,
                "value_area_low": None, "value_area_high": None,
                "total_days": len(valid)}

    lo = min(valid)
    hi = max(valid)
    if hi == lo:
        # All same price — single bin.
        return {"bins": [{"label": f"{lo:.2f}", "low": lo, "high": hi,
                          "count": len(valid), "color": "#ef4444"}],
                "max_count": len(valid), "poc_label": f"{lo:.2f}",
                "value_area_low": lo, "value_area_high": hi,
                "total_days": len(valid)}

    bin_width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for c in valid:
        idx = int((c - lo) / bin_width)
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1

    max_count = max(counts)
    total = len(valid)

    # Heatmap color: blue (low) → yellow (mid) → red (high).
    def _heatmap_color(count: int) -> str:
        if max_count == 0:
            return "#3b82f6"
        ratio = count / max_count
        if ratio < 0.5:
            # blue → yellow interpolation
            t = ratio / 0.5
            r = int(59 + (250 - 59) * t)
            g = int(130 + (204 - 130) * t)
            b = int(246 + (21 - 246) * t)
        else:
            # yellow → red interpolation
            t = (ratio - 0.5) / 0.5
            r = int(250 + (239 - 250) * t)
            g = int(204 + (68 - 204) * t)
            b = int(21 + (68 - 21) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    bins: list[dict] = []
    for i in range(n_bins):
        bin_lo = lo + i * bin_width
        bin_hi = bin_lo + bin_width
        bins.append({
            "label": f"{bin_lo:.2f}",
            "low": bin_lo,
            "high": bin_hi,
            "count": counts[i],
            "color": _heatmap_color(counts[i]),
        })

    # Point of Control (highest bin).
    poc_idx = counts.index(max_count)
    poc_label = bins[poc_idx]["label"]

    # Value Area: expand from POC until ~70% of total is covered.
    target = int(total * 0.7)
    va_low_idx = poc_idx
    va_high_idx = poc_idx
    covered = counts[poc_idx]
    while covered < target and (va_low_idx > 0 or va_high_idx < n_bins - 1):
        # Expand to whichever side has more count.
        left_count = counts[va_low_idx - 1] if va_low_idx > 0 else -1
        right_count = counts[va_high_idx + 1] if va_high_idx < n_bins - 1 else -1
        if right_count >= left_count and va_high_idx < n_bins - 1:
            va_high_idx += 1
            covered += counts[va_high_idx]
        elif va_low_idx > 0:
            va_low_idx -= 1
            covered += counts[va_low_idx]
        else:
            break

    return {
        "bins": bins,
        "max_count": max_count,
        "poc_label": poc_label,
        "value_area_low": bins[va_low_idx]["low"],
        "value_area_high": bins[va_high_idx]["high"],
        "total_days": total,
    }
