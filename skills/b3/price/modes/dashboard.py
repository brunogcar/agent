"""Mode: dashboard -- 8-tab B3 price analytics dashboard.

Tabs:
  Cotação         (group: Preço)             — candlestick + volume + 6 KPIs
  Médias Móveis   (group: Preço)             — SMA chart + crossovers table
  Volume          (group: Preço)             — volume bars + price overlay + stats
  Indicadores     (group: Preço)             — RSI + MACD + Stochastic + OBV + ADX + CCI + Williams %R  [v1.6]
  Retornos        (group: Performance)       — cumulative return (raw + adjusted) + drawdown
  Volatilidade    (group: Performance)       — rolling vol + Bollinger Bands
  Fibonacci       (group: Análise Técnica)   — Fib levels + trade setup (COMPRA/VENDA)  [v1.3]
  Bid-Ask Spread  (group: Liquidez)             — spread absoluto + spread % + bid/ask/close + liquidez KPI  [v1.6]

Workflow:
  1. Fetch 10 years of daily OHLCV from cotahist.db via engines.ohlcv_series
  2. Compute MAs, returns, drawdowns, volatility, Bollinger Bands via engines
  3. Compute RSI, MACD, Stochastic, OBV via engines (momentum oscillators)
  4. [v1.3] Compute dividend-adjusted close + swing extremes + Fibonacci trade setup
  5. Find MA crossovers (MA20×MA50, MA50×MA200)
  6. Get 52-week range + latest quote
  7. Pass computed series to report builders (no computation in builders)
"""
from __future__ import annotations

from datetime import datetime as _dt
from datetime import date as _date, timedelta as _timedelta

from skills.b3.price._registry import register_mode
from skills.b3.price.engines import (
    ohlcv_series, latest_quote, compute_sma, compute_returns,
    compute_cumulative_returns, compute_drawdowns, compute_volatility,
    compute_bollinger_bands, find_ma_crossovers, compute_52w_range,
    compute_rsi, compute_macd, compute_stochastic, compute_obv,
    compute_adx, compute_cci, compute_williams_r,
    compute_bid_ask_spread, compute_spread_pct,
    compute_adjusted_close, find_swing_extremes,
    compute_price_snapshot, compute_period_returns,
    compute_annual_returns, compute_price_histogram,
)
from skills.b3.price.report import (
    build_cotacao_sections, build_quote_kpis,
    build_medias_sections, build_volume_sections,
    build_retornos_sections, build_volatilidade_sections,
    build_indicadores_sections, build_fibonacci_sections,
    build_spread_sections,
)

def _today_iso() -> str:
    return _date.today().isoformat()


def _ten_years_ago_iso() -> str:
    return (_date.today() - _timedelta(days=365 * 10)).isoformat()





@register_mode(
    "dashboard",
    description=(
        "B3 price analytics dashboard. 8 tabs: Cotação (candlestick + volume + KPIs), "
        "Médias Móveis (SMA20/50/100/200 + crossovers), Volume (bars + price overlay), "
        "Indicadores (RSI + MACD + Stochastic + OBV + ADX + CCI + Williams %R + signals), "
        "Retornos (cumulative + adjusted + drawdown), "
        "Volatilidade (rolling vol + Bollinger), "
        "Fibonacci (levels + COMPRA/VENDA trade setup), "
        "Bid-Ask Spread (spread absoluto + % + bid/ask/close + liquidez), "
        "Bid-Ask Spread (spread absoluto + % + bid/ask/close + liquidez)."
    ),
    params={"ticker": "str. Required. B3 ticker (e.g. PETR4)."},
    include_in_all=False,
    examples=[
        'skill(domain="b3", sub_domain="price", mode="dashboard", '
        'params=\'{"ticker":"PETR4"}\')',
    ],
)
def dashboard(ticker: str = "") -> dict:
    """Build the 9-tab B3 price dashboard for a single ticker.

    [v1.7] Added 9th "Opções" tab — embeds the Cadeia de Opções (calls + puts
    + legend) from the b3/options skill. Cross-skill integration: if the
    options skill is missing or has no options for the ticker, the tab
    shows a graceful "Sem opções disponíveis" text section.
    """
    _t0 = _dt.now()
    print(f"[b3.price] Starting dashboard for {ticker!r}...", flush=True)

    if not ticker or not ticker.strip():
        return {"status": "error", "error": "ticker is required"}

    tk = ticker.strip().upper()
    date_from = _ten_years_ago_iso()
    date_to = _today_iso()

    # ── Section 1/5: Fetch OHLCV ───────────────────────────────────────────
    _s_t0 = _dt.now()
    ohlcv = ohlcv_series(tk, date_from, date_to)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] OHLCV fetched: {len(ohlcv)} rows ({_s_elapsed:.1f}s)", flush=True)

    if not ohlcv or len(ohlcv) < 2:
        return {
            "status": "error",
            "ticker": tk,
            "error": f"no OHLCV data for {tk} in {date_from}..{date_to}",
        }

    dates = [p["date"] for p in ohlcv]
    closes = [p["close"] for p in ohlcv]
    volumes = [p.get("volume") or 0.0 for p in ohlcv]
    opens = [p.get("open") for p in ohlcv]

    # ── Section 2/5: Compute indicators ────────────────────────────────────
    _s_t0 = _dt.now()
    ma20 = compute_sma(closes, 20)
    ma50 = compute_sma(closes, 50)
    ma100 = compute_sma(closes, 100)
    ma200 = compute_sma(closes, 200)
    returns = compute_returns(closes)
    cum_returns = compute_cumulative_returns(closes)
    drawdowns = compute_drawdowns(closes)
    vol_20d = compute_volatility(returns, 20)
    vol_60d = compute_volatility(returns, 60)
    vol_252d = compute_volatility(returns, 252)
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(closes, period=20, num_std=2.0)
    # [v1.2] Momentum oscillators — RSI, MACD, Stochastic, OBV.
    rsi = compute_rsi(closes, period=14)
    macd_line, signal_line, histogram = compute_macd(closes, fast=12, slow=26, signal=9)
    highs = [p.get("high") for p in ohlcv]
    lows = [p.get("low") for p in ohlcv]
    k_line, d_line = compute_stochastic(highs, lows, closes, k_period=14, d_period=3)
    obv = compute_obv(closes, volumes)
    # [v1.6] Trend + cyclical indicators -- ADX (trend strength),
    # CCI (cyclical oscillator), Williams %R (momentum 0 to -100).
    adx = compute_adx(highs, lows, closes, period=14)
    cci = compute_cci(highs, lows, closes, period=20)
    williams_r = compute_williams_r(highs, lows, closes, period=14)
    # [v1.6] Bid-ask spread series (for the new Bid-Ask Spread tab).
    best_bids = [p.get("best_bid") for p in ohlcv]
    best_asks = [p.get("best_ask") for p in ohlcv]
    spreads = compute_bid_ask_spread(best_bids, best_asks)
    spread_pcts = compute_spread_pct(best_bids, best_asks, closes)
    # [v1.3] Dividend-adjusted close (backward adjustment) + Fibonacci swing extremes.
    adjusted_closes, div_adjustments = compute_adjusted_close(tk, dates, closes)
    adj_cum_returns = compute_cumulative_returns(adjusted_closes)
    swings = [
        find_swing_extremes(dates, highs, lows, lookback_days=lb["days"])
        for lb in [
            {"label": "Swing_4",  "days": 30},
            {"label": "Swing_12", "days": 90},
            {"label": "Swing_52", "days": 365},
        ]
    ]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] Indicators computed ({_s_elapsed:.1f}s)", flush=True)

    # ── Section 3/5: Find crossovers ───────────────────────────────────────
    _s_t0 = _dt.now()
    cross_20_50 = find_ma_crossovers(dates, ma20, ma50, "MA20", "MA50")
    cross_50_200 = find_ma_crossovers(dates, ma50, ma200, "MA50", "MA200")
    crossovers = cross_20_50 + cross_50_200
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Crossovers found: {len(cross_20_50)} (MA20×MA50) + "
        f"{len(cross_50_200)} (MA50×MA200) ({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Section 4/5: 52-week range + latest quote + prev close ────────────
    _s_t0 = _dt.now()
    range_52w = compute_52w_range(tk, date_to)
    quote = latest_quote(tk)
    # Previous close = the close right before the latest day in `ohlcv`.
    prev_close = closes[-2] if len(closes) >= 2 else None
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Quote={quote.get('close') if quote else None} "
        f"52w=[{range_52w.get('low_52w')}..{range_52w.get('high_52w')}] "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # [v1.4] Cotação tab enhancements: price snapshot, period returns,
    # annual returns, price histogram. Computed here (after range_52w).
    price_snapshot = compute_price_snapshot(ohlcv, range_52w)
    period_returns = compute_period_returns(dates, closes)
    annual_returns = compute_annual_returns(dates, closes)
    price_histogram = compute_price_histogram(closes, n_bins=30)

    # ── Section 5/5: Build KPIs + 5 tab sections via builders ──────────────
    _s_t0 = _dt.now()
    kpis = build_quote_kpis(quote, prev_close, range_52w)

    cotacao_sections = build_cotacao_sections(
        tk, ohlcv, ma20, ma50, ma100, ma200,
        snapshot=price_snapshot,
        period_returns=period_returns,
        annual_returns=annual_returns,
        histogram=price_histogram,
    )
    # [v5] Company header + b3 dividends sync (per-ticker)
    try:
        from skills.cvm._shared_report.company_header import build_company_header

        # Sync b3 dividends for this ticker (needed for Fibonacci adjusted returns)
        try:
            from data_sources.b3.dividends.sync_engine import sync as _div_sync
            _div_sync(ticker=tk)
        except Exception:
            pass

        # Sync CVM DBs for company header
        for _sync_mod, _sync_fn, _sync_kwargs in [
            ("data_sources.cvm.cad.sync_engine", "sync", {}),
            ("data_sources.cvm.fca.sync_engine", "sync", {}),
            ("data_sources.cvm.bridge.sync_engine", "sync", {"ticker": tk}),
        ]:
            try:
                _mod = __import__(_sync_mod, fromlist=[_sync_fn])
                _sync = getattr(_mod, _sync_fn)
                _sync(**_sync_kwargs)
            except Exception:
                pass

        company_header = build_company_header(tk)
        if company_header and company_header.get("ticker") and company_header.get("name"):
            cotacao_sections.insert(0, {
                "type": "company_info",
                "company_header": company_header,
            })
        else:
            cotacao_sections.insert(0, {
                "type": "text",
                "title": f"Cotação — {tk}",
                "text": (
                    f"Período: {dates[0]} a {dates[-1]} • {len(dates)} pregões • "
                    f"Fonte: B3 COTAHIST (mercado: lote padrão)"
                ),
            })
    except Exception:
        cotacao_sections.insert(0, {
            "type": "text",
            "title": f"Cotação — {tk}",
            "text": (
                f"Período: {dates[0]} a {dates[-1]} • {len(dates)} pregões • "
                f"Fonte: B3 COTAHIST (mercado: lote padrão)"
            ),
        })

    medias_sections = build_medias_sections(
        tk, dates, closes, ma20, ma50, ma100, ma200, crossovers,
    )
    volume_sections = build_volume_sections(
        tk, dates, volumes, closes, opens,
        trade_counts=[p.get("trade_count") for p in ohlcv],
        contracts=[p.get("contracts") for p in ohlcv],
    )
    # [v1.2] Indicadores tab — RSI + MACD + Stochastic + OBV + signals table.
    # [v1.6] + ADX + CCI + Williams %R charts + signals rows.
    indicadores_sections = build_indicadores_sections(
        tk, dates, closes, highs, lows, volumes,
        rsi, macd_line, signal_line, histogram,
        k_line, d_line, obv,
        adx=adx, cci=cci, williams_r=williams_r,
    )
    retornos_sections = build_retornos_sections(
        tk, dates, closes, cum_returns, drawdowns,
        adj_cum_returns=adj_cum_returns,
    )
    volatilidade_sections = build_volatilidade_sections(
        tk, dates, closes, vol_20d, vol_60d, vol_252d,
        bb_upper, bb_middle, bb_lower,
    )
    # [v1.3] Fibonacci tab — price chart with Fib levels + trade setup.
    current_price = closes[-1] if closes else None
    fibonacci_sections = build_fibonacci_sections(
        tk, dates, closes, highs, lows, current_price,
        swings, div_adjustments,
    )
    # [v1.6] Bid-Ask Spread tab — spread charts + bid/ask/close + liquidez KPI.
    spread_sections = build_spread_sections(
        tk, dates, best_bids, best_asks, closes,
        volumes=volumes,
        trade_counts=[p.get("trade_count") for p in ohlcv],
    )
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] Sections built ({_s_elapsed:.1f}s)", flush=True)

    tabs = [
        {"name": "Cotação",       "group": "Preço",             "sections": cotacao_sections},
        {"name": "Médias Móveis", "group": "Preço",             "sections": medias_sections},
        {"name": "Volume",        "group": "Preço",             "sections": volume_sections},
        {"name": "Indicadores",  "group": "Preço",             "sections": indicadores_sections},
        {"name": "Retornos",      "group": "Performance",       "sections": retornos_sections},
        {"name": "Volatilidade",  "group": "Performance",       "sections": volatilidade_sections},
        {"name": "Fibonacci",     "group": "Análise Técnica",  "sections": fibonacci_sections},
        {"name": "Bid-Ask Spread", "group": "Liquidez",           "sections": spread_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(
        f"[b3.price] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.",
        flush=True,
    )

    return {
        "status": "ok",
        "ticker": tk,
        "title": f"Price Dashboard — {tk}",
        "tabs": tabs,
        "kpis": kpis,
        "period": {"from": dates[0], "to": dates[-1], "days": len(dates)},
        "crossovers": {
            "ma20_x_ma50":  len(cross_20_50),
            "ma50_x_ma200": len(cross_50_200),
        },
    }
