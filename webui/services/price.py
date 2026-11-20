"""webui/services/price.py — price data service.

[WebUI v1.2] Wraps skills/b3/price/engines for the WebUI. Direct imports,
NOT through the MCP dispatcher.

Provides:
  - ohlcv + moving averages (for candlestick chart)
  - price snapshot (for the Preço tab tables)
  - period returns + annual returns (for the Preço tab tables)
  - price histogram (for the Preço tab chart)

[WebUI v1.5] HARDENING:
  - Shared TTL OHLCV cache: price_data/indicators/volatility/volume each
    used to re-read the SAME 10-year series from SQLite (4-5 identical
    full scans per Preço tab visit). _ohlcv() caches per (ticker, window)
    for 60s — one scan serves all subtabs.
  - ohlcv_with_mas body_data: rows with open NULL/0 now fall back to the
    close (a 0-open bar drew a candle from 0 → close and wrecked the
    y-axis).
  - fibonacci: swing window cutoffs anchor on the LAST DATA DATE (was
    date.today() — stale cotahist silently shrank the windows); the unused
    adjusted_closes variable is gone.
  - PT-BR error strings (English internals no longer reach the UI);
    exceptions logged server-side.
"""
from __future__ import annotations

import sys
import time
import traceback
from datetime import date, timedelta
from typing import Any

# TTL for the shared OHLCV cache (seconds). Short enough that a sync is
# picked up quickly, long enough that the 4 Preço subtabs + a Visão Geral
# chart share ONE 10-year scan.
_OHLCV_TTL = 60.0


def _log_err(where: str, e: Exception) -> None:
    print(f"[webui] {where} failed: {e}\n{traceback.format_exc()}", file=sys.stderr)


class PriceService:
    """Price data service — wraps b3.price engines."""

    def __init__(self) -> None:
        # (ticker, date_from, date_to) → (fetched_at_monotonic, rows)
        self._ohlcv_cache: dict[tuple[str, str, str], tuple[float, list]] = {}

    # ── shared cached OHLCV fetch ───────────────────────────────────────────

    def _ohlcv(self, ticker: str, years: float) -> list[dict]:
        """Cached ohlcv_series() — one 10y scan serves every subtab (60s TTL)."""
        from skills.b3.price.engines import ohlcv_series
        date_to = date.today().isoformat()
        days = int(years * 365.25)
        date_from = (date.today() - timedelta(days=days)).isoformat()
        key = (ticker.upper(), date_from, date_to)
        hit = self._ohlcv_cache.get(key)
        if hit and (time.monotonic() - hit[0]) < _OHLCV_TTL:
            return hit[1]
        rows = ohlcv_series(ticker.upper(), date_from, date_to) or []
        self._ohlcv_cache[key] = (time.monotonic(), rows)
        return rows

    # ── candlestick ──────────────────────────────────────────────────────────

    def ohlcv_with_mas(self, ticker: str, years: float = 1) -> dict[str, Any]:
        """Get OHLCV data + moving averages for the candlestick chart.

        Returns: {labels, ohlc, body_data, ma20, ma50, ma100, ma200}
        """
        try:
            from skills.b3.price.engines import compute_sma
            ohlcv = self._ohlcv(ticker, years)
            if not ohlcv:
                return {"labels": [], "ohlc": [], "body_data": [], "ma20": [], "ma50": [], "ma100": [], "ma200": []}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            ma20 = compute_sma(closes, 20)
            ma50 = compute_sma(closes, 50)
            ma100 = compute_sma(closes, 100)
            ma200 = compute_sma(closes, 200)

            ohlc_data = []
            body_data = []
            for p in ohlcv:
                c = p.get("close")
                # [v1.5] open NULL/0 → fall back to close. The old
                # `p.get("open") or 0` drew a 0→close bar and crushed the
                # y-axis whenever COTAHIST had a missing open.
                o = p.get("open") or c
                if o is None or c is None:
                    ohlc_data.append({"o": None, "h": p.get("high"), "l": p.get("low"), "c": c})
                    body_data.append([None, None])
                    continue
                ohlc_data.append({"o": o, "h": p.get("high"), "l": p.get("low"), "c": c})
                body_data.append([min(o, c), max(o, c)])
            return {
                "labels": dates,
                "ohlc": ohlc_data,
                "body_data": body_data,
                "ma20": ma20,
                "ma50": ma50,
                "ma100": ma100,
                "ma200": ma200,
                "closes": closes,
            }
        except Exception as e:
            _log_err(f"ohlcv_with_mas({ticker})", e)
            return {"_error": "erro ao carregar dados de preço"}

    def price_data(self, ticker: str) -> dict[str, Any]:
        """Full price data for the Preço tab: snapshot, returns, histogram."""
        try:
            from skills.b3.price.engines import (
                compute_52w_range,
                compute_price_snapshot, compute_period_returns,
                compute_annual_returns, compute_price_histogram,
                latest_quote,
            )
            ohlcv = self._ohlcv(ticker, 10)
            if not ohlcv or len(ohlcv) < 2:
                return {"_error": "sem dados de cotação"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            range_52w = compute_52w_range(ticker.upper(), dates[-1])
            snapshot = compute_price_snapshot(ohlcv, range_52w)
            period_returns = compute_period_returns(dates, closes)
            annual_returns = compute_annual_returns(dates, closes)
            histogram = compute_price_histogram(closes, n_bins=30)
            quote = latest_quote(ticker.upper())
            prev_close = closes[-2] if len(closes) >= 2 else None

            return {
                "snapshot": snapshot,
                "period_returns": period_returns,
                "annual_returns": annual_returns,
                "histogram": histogram,
                "quote": quote,
                "prev_close": prev_close,
                "range_52w": range_52w,
                "dates": dates,
                "closes": closes,
            }
        except Exception as e:
            _log_err(f"price_data({ticker})", e)
            return {"_error": "erro ao carregar dados de preço"}

    def indicators(self, ticker: str) -> dict[str, Any]:
        """Technical indicators for the Indicadores subtab.

        Full set: RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R.
        """
        try:
            from skills.b3.price.engines import (
                compute_rsi, compute_macd, compute_stochastic,
                compute_obv, compute_adx, compute_cci, compute_williams_r,
            )
            ohlcv = self._ohlcv(ticker, 10)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "dados insuficientes para indicadores"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            highs = [p.get("high") for p in ohlcv]
            lows = [p.get("low") for p in ohlcv]
            volumes = [p.get("volume") or 0.0 for p in ohlcv]

            rsi = compute_rsi(closes, period=14)
            macd_line, signal_line, histogram = compute_macd(closes, fast=12, slow=26, signal=9)
            k_line, d_line = compute_stochastic(highs, lows, closes, k_period=14, d_period=3)
            obv = compute_obv(closes, volumes)
            adx = compute_adx(highs, lows, closes, period=14)
            cci = compute_cci(highs, lows, closes, period=20)
            williams_r = compute_williams_r(highs, lows, closes, period=14)

            return {
                "dates": dates,
                "closes": closes,
                "rsi": rsi,
                "macd_line": macd_line,
                "signal_line": signal_line,
                "macd_histogram": histogram,
                "k_line": k_line,
                "d_line": d_line,
                "obv": obv,
                "adx": adx,
                "cci": cci,
                "williams_r": williams_r,
            }
        except Exception as e:
            _log_err(f"indicators({ticker})", e)
            return {"_error": "erro ao calcular indicadores"}

    def volatility(self, ticker: str) -> dict[str, Any]:
        """Volatility data for the Volatilidade subtab: Bollinger Bands + rolling vol."""
        try:
            from skills.b3.price.engines import (
                compute_returns, compute_volatility,
                compute_bollinger_bands,
            )
            ohlcv = self._ohlcv(ticker, 10)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "dados insuficientes para volatilidade"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            returns = compute_returns(closes)
            vol_20d = compute_volatility(returns, 20)
            vol_60d = compute_volatility(returns, 60)
            vol_252d = compute_volatility(returns, 252)
            bb_upper, bb_middle, bb_lower = compute_bollinger_bands(closes, period=20, num_std=2.0)

            return {
                "dates": dates,
                "closes": closes,
                "vol_20d": vol_20d,
                "vol_60d": vol_60d,
                "vol_252d": vol_252d,
                "bb_upper": bb_upper,
                "bb_middle": bb_middle,
                "bb_lower": bb_lower,
            }
        except Exception as e:
            _log_err(f"volatility({ticker})", e)
            return {"_error": "erro ao calcular volatilidade"}

    def volume(self, ticker: str) -> dict[str, Any]:
        """Volume data for the Volume subtab: volume bars + trade count + contracts."""
        try:
            from skills.b3.price.engines import compute_sma
            ohlcv = self._ohlcv(ticker, 10)
            if not ohlcv or len(ohlcv) < 2:
                return {"_error": "sem dados de volume"}

            dates = [p["date"] for p in ohlcv]
            volumes = [p.get("volume") or 0.0 for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            opens = [p.get("open") for p in ohlcv]
            trade_counts = [p.get("trade_count") or 0 for p in ohlcv]
            contracts = [p.get("contracts") or 0 for p in ohlcv]
            vol_ma20 = compute_sma(volumes, 20)

            # Stats
            valid_vols = [v for v in volumes if v and v > 0]
            avg_vol = sum(valid_vols) / len(valid_vols) if valid_vols else 0
            max_vol = max(valid_vols) if valid_vols else 0
            min_vol = min(valid_vols) if valid_vols else 0
            latest_vol = volumes[-1] if volumes else 0

            return {
                "dates": dates,
                "volumes": volumes,
                "closes": closes,
                "opens": opens,
                "trade_counts": trade_counts,
                "contracts": contracts,
                "vol_ma20": vol_ma20,
                "stats": {
                    "avg_volume": avg_vol,
                    "max_volume": max_vol,
                    "min_volume": min_vol,
                    "latest_volume": latest_vol,
                    "latest_trades": trade_counts[-1] if trade_counts else 0,
                    "latest_contracts": contracts[-1] if contracts else 0,
                },
            }
        except Exception as e:
            _log_err(f"volume({ticker})", e)
            return {"_error": "erro ao carregar volume"}

    def fibonacci(self, ticker: str) -> dict[str, Any]:
        """Fibonacci data for the Fibonacci subtab: swing extremes + levels + trade setups."""
        try:
            from skills.b3.price.engines import (
                find_swing_extremes,
                compute_fibonacci_levels, compute_fibonacci_trade_setup,
                compute_adjusted_close,
            )
            ohlcv = self._ohlcv(ticker, 1)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "dados insuficientes para fibonacci"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            highs = [p.get("high") for p in ohlcv]
            lows = [p.get("low") for p in ohlcv]
            current_price = closes[-1] if closes else None

            # [v1.5] Anchor windows on the LAST DATA DATE (was date.today():
            # stale cotahist silently shrank the 4/12/52-week windows).
            from datetime import date as _date, timedelta as _timedelta
            last_date = _date.fromisoformat(dates[-1]) if dates else _date.today()

            # 3 swing timeframes: 4 weeks, 12 weeks, 52 weeks
            swings = []
            for lb in [30, 90, 365]:
                swing = find_swing_extremes(dates, highs, lows, lookback_days=lb)
                if swing.get("high_price") and swing.get("low_price"):
                    levels = compute_fibonacci_levels(swing["high_price"], swing["low_price"])
                    setup = compute_fibonacci_trade_setup(swing["high_price"], swing["low_price"])
                    swing["levels"] = levels
                    swing["setup"] = setup
                    swing["current_price"] = current_price
                    # Store dates + closes for the chart (within the lookback window)
                    cutoff = (last_date - _timedelta(days=lb)).isoformat()
                    swing["_dates"] = [d for d in dates if d >= cutoff]
                    swing["_closes"] = [c for d, c in zip(dates, closes) if d >= cutoff]
                    swings.append(swing)

            # Dividend adjustments (adjusted_closes itself is unused here —
            # only the adjustment events are shown in the UI).
            _adjusted, div_adjustments = compute_adjusted_close(ticker.upper(), dates, closes)

            return {
                "swings": swings,
                "dividend_adjustments": div_adjustments,
                "current_price": current_price,
            }
        except Exception as e:
            _log_err(f"fibonacci({ticker})", e)
            return {"_error": "erro ao calcular fibonacci"}
