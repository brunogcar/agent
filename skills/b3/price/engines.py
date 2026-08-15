"""skills/b3/price/engines.py -- OHLCV + technical analysis engines.

Queries cotahist.db for daily OHLCV data and computes technical indicators:
  - Moving averages (SMA20/50/100/200, EMA for MACD)
  - Volume + volume MA
  - Returns (daily, cumulative, drawdown)
  - Volatility (rolling 20D/60D/252D)
  - Bollinger Bands (20, 2σ)
  - Momentum oscillators (RSI, MACD, Stochastic, OBV)  [v1.2]

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

    Returns: [{"date", "open", "high", "low", "close", "volume", "trade_count"}]
    sorted oldest-first.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            """SELECT refdate, open, high, low, close, volume, trade_count
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
