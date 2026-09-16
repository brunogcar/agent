"""webui/services/price.py — price data service.

[WebUI v1.2] Wraps skills/b3/price/engines for the WebUI. Direct imports,
NOT through the MCP dispatcher.

Provides:
  - ohlcv + moving averages (for candlestick chart)
  - price snapshot (for the Preço tab tables)
  - period returns + annual returns (for the Preço tab tables)
  - price histogram (for the Preço tab chart)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class PriceService:
    """Price data service — wraps b3.price engines."""

    def ohlcv_with_mas(self, ticker: str, years: float = 1) -> dict[str, Any]:
        """Get OHLCV data + moving averages for the candlestick chart.

        Returns: {labels, ohlc, body_data, ma20, ma50, ma100, ma200}
        """
        try:
            from skills.b3.price.engines import ohlcv_series, compute_sma
            date_to = date.today().isoformat()
            days = int(years * 365.25)
            date_from = (date.today() - timedelta(days=days)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv:
                return {"labels": [], "ohlc": [], "body_data": [], "ma20": [], "ma50": [], "ma100": [], "ma200": []}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            ma20 = compute_sma(closes, 20)
            ma50 = compute_sma(closes, 50)
            ma100 = compute_sma(closes, 100)
            ma200 = compute_sma(closes, 200)

            ohlc_data = [
                {"o": p.get("open"), "h": p.get("high"), "l": p.get("low"), "c": p.get("close")}
                for p in ohlcv
            ]
            body_data = [
                [min(p.get("open") or 0, p.get("close") or 0),
                 max(p.get("open") or 0, p.get("close") or 0)]
                for p in ohlcv
            ]
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
            return {"_error": str(e)}

    def price_data(self, ticker: str) -> dict[str, Any]:
        """Full price data for the Preço tab: snapshot, returns, histogram.

        Uses 10 years of data (same as the price dashboard).
        """
        try:
            from skills.b3.price.engines import (
                ohlcv_series, compute_sma, compute_52w_range,
                compute_price_snapshot, compute_period_returns,
                compute_annual_returns, compute_price_histogram,
                latest_quote,
            )
            date_to = date.today().isoformat()
            date_from = (date.today() - timedelta(days=365 * 10)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv or len(ohlcv) < 2:
                return {"_error": "no OHLCV data"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            range_52w = compute_52w_range(ticker.upper(), date_to)
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
            return {"_error": str(e)}

    def indicators(self, ticker: str) -> dict[str, Any]:
        """Technical indicators for the Indicadores subtab.

        Full set: RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R.
        Uses 10 years of data (same as the price dashboard).
        """
        try:
            from skills.b3.price.engines import (
                ohlcv_series, compute_rsi, compute_macd, compute_stochastic,
                compute_obv, compute_adx, compute_cci, compute_williams_r,
            )
            date_to = date.today().isoformat()
            date_from = (date.today() - timedelta(days=365 * 10)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "insufficient data for indicators"}

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
            return {"_error": str(e)}

    def volatility(self, ticker: str) -> dict[str, Any]:
        """Volatility data for the Volatilidade subtab: Bollinger Bands + rolling vol.

        Uses 10 years of data (same as the price dashboard).
        """
        try:
            from skills.b3.price.engines import (
                ohlcv_series, compute_returns, compute_volatility,
                compute_bollinger_bands,
            )
            date_to = date.today().isoformat()
            date_from = (date.today() - timedelta(days=365 * 10)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "insufficient data for volatility"}

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
            return {"_error": str(e)}

    def volume(self, ticker: str) -> dict[str, Any]:
        """Volume data for the Volume subtab: volume bars + trade count + contracts.

        Uses 10 years of data (same as indicators + volatility).
        """
        try:
            from skills.b3.price.engines import ohlcv_series, compute_sma
            date_to = date.today().isoformat()
            date_from = (date.today() - timedelta(days=365 * 10)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv or len(ohlcv) < 2:
                return {"_error": "insufficient data for volume"}

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
            return {"_error": str(e)}

    def fibonacci(self, ticker: str) -> dict[str, Any]:
        """Fibonacci data for the Fibonacci subtab: swing extremes + levels + trade setups."""
        try:
            from skills.b3.price.engines import (
                ohlcv_series, find_swing_extremes,
                compute_fibonacci_levels, compute_fibonacci_trade_setup,
                compute_adjusted_close,
            )
            date_to = date.today().isoformat()
            date_from = (date.today() - timedelta(days=365)).isoformat()
            ohlcv = ohlcv_series(ticker.upper(), date_from, date_to)
            if not ohlcv or len(ohlcv) < 30:
                return {"_error": "insufficient data for fibonacci"}

            dates = [p["date"] for p in ohlcv]
            closes = [p["close"] for p in ohlcv]
            highs = [p.get("high") for p in ohlcv]
            lows = [p.get("low") for p in ohlcv]
            current_price = closes[-1] if closes else None

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
                    from datetime import date as _date, timedelta as _timedelta
                    cutoff = (_date.today() - _timedelta(days=lb)).isoformat()
                    swing["_dates"] = [d for d in dates if d >= cutoff]
                    swing["_closes"] = [c for d, c in zip(dates, closes) if d >= cutoff]
                    swings.append(swing)

            # Dividend adjustments
            adjusted_closes, div_adjustments = compute_adjusted_close(ticker.upper(), dates, closes)

            return {
                "swings": swings,
                "dividend_adjustments": div_adjustments,
                "current_price": current_price,
            }
        except Exception as e:
            return {"_error": str(e)}
