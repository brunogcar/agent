"""skills/b3/price/engines.py -- OHLCV + technical analysis engines.

Queries cotahist.db for daily OHLCV data and computes technical indicators:
  - Moving averages (SMA20/50/100/200)
  - Volume + volume MA
  - Returns (daily, cumulative, drawdown)
  - Volatility (rolling 20D/60D/252D)
  - Bollinger Bands (20, 2σ)

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
