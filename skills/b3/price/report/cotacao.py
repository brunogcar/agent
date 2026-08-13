"""skills/b3/price/report/cotacao.py -- Cotação tab builders.

Builds the candlestick + volume + KPI sections for the Cotação tab.

Builders are pure data shape — they accept already-computed values
(OHLCV rows, MAs, latest quote, 52-week range) and emit section dicts
that the dashboard template knows how to render. NO computation here.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import (
    fmt_brl, fmt_pct, fmt_int, fmt_compact, _is_missing,
)


# ── KPI cards ────────────────────────────────────────────────────────────────

def build_quote_kpis(quote: dict | None, prev_close: float | None,
                     range_52w: dict | None) -> list[dict]:
    """Build 6 KPI cards for the Cotação tab.

    Args:
        quote:       latest_quote() result — {date, open, high, low, close, volume, ...}
        prev_close:  prior trading day close (for intraday variation %)
        range_52w:   compute_52w_range() result — {high_52w, low_52w}

    Returns:
        List of 6 KPI section dicts: Preço, Variação %, Abertura, Máxima, Mínima, Volume.
    """
    if not quote:
        return [
            {"type": "kpi", "label": "Preço",          "value": "—", "unit": "", "subtitle": ""},
            {"type": "kpi", "label": "Variação (dia)", "value": "—", "unit": "", "subtitle": ""},
            {"type": "kpi", "label": "Abertura",       "value": "—", "unit": "", "subtitle": ""},
            {"type": "kpi", "label": "Máxima",         "value": "—", "unit": "", "subtitle": ""},
            {"type": "kpi", "label": "Mínima",         "value": "—", "unit": "", "subtitle": ""},
            {"type": "kpi", "label": "Volume",         "value": "—", "unit": "", "subtitle": ""},
        ]

    close = quote.get("close")
    open_ = quote.get("open")
    high = quote.get("high")
    low = quote.get("low")
    volume = quote.get("volume") or 0.0
    qdate = quote.get("date", "")

    # Variation % vs prior close (intraday)
    if prev_close and prev_close > 0 and not _is_missing(close):
        var_pct = (close - prev_close) / prev_close
        var_str = fmt_pct(var_pct)
        delta = ("+" if var_pct >= 0 else "") + var_str
    else:
        var_str = "—"
        delta = None

    # 52w range subtitle
    sub_52w = ""
    if range_52w and range_52w.get("high_52w") and range_52w.get("low_52w"):
        sub_52w = (
            f"52s: {fmt_brl(range_52w['low_52w'], suffix=False)} – "
            f"{fmt_brl(range_52w['high_52w'], suffix=False)}"
        )

    return [
        {
            "type": "kpi",
            "label": "Preço",
            "value": fmt_brl(close, suffix=False),
            "unit": "",
            "subtitle": qdate,
            "delta": delta,
        },
        {
            "type": "kpi",
            "label": "Variação (dia)",
            "value": var_str,
            "unit": "",
            "subtitle": "vs. fechamento anterior",
        },
        {
            "type": "kpi",
            "label": "Abertura",
            "value": fmt_brl(open_, suffix=False),
            "unit": "",
            "subtitle": "",
        },
        {
            "type": "kpi",
            "label": "Máxima",
            "value": fmt_brl(high, suffix=False),
            "unit": "",
            "subtitle": sub_52w,
        },
        {
            "type": "kpi",
            "label": "Mínima",
            "value": fmt_brl(low, suffix=False),
            "unit": "",
            "subtitle": "",
        },
        {
            "type": "kpi",
            "label": "Volume",
            "value": fmt_compact(volume),
            "unit": "R$",
            "subtitle": f"{fmt_int(quote.get('trade_count') or 0)} negócios",
        },
    ]


# ── Candlestick + Volume sections ────────────────────────────────────────────

# Candle / volume bar colors — green if close >= open (up day), red otherwise.
_COLOR_UP = "#22c55e"
_COLOR_DOWN = "#ef4444"

# MA line colors (distinct hues, AA contrast on dark/light themes).
_MA_COLORS = {
    "MA20":  "#facc15",  # yellow
    "MA50":  "#fb923c",  # orange
    "MA100": "#ec4899",  # pink
    "MA200": "#ef4444",  # red
}

# Price-line color used on dual-axis overlays (Volume Diário, etc.).
_PRICE_COLOR = "#0d9488"  # teal


def _ma_dataset(label: str, data: list, color: str) -> dict:
    """Build a moving-average line dataset for the candlestick overlay."""
    return {
        "type": "line",
        "label": label,
        "data": data,
        "borderColor": color,
        "borderWidth": 1.5,
        "pointRadius": 0,
        "pointHoverRadius": 3,
        "tension": 0,
        "fill": False,
    }


def build_cotacao_sections(
    ticker: str,
    ohlcv: list[dict],
    ma20: list[float | None],
    ma50: list[float | None],
    ma100: list[float | None],
    ma200: list[float | None],
) -> list[dict]:
    """Build the Cotação tab: OHLC candlestick chart + volume bars (with price).

    [v2] The candlestick is now a VANILLA Chart.js chart rendered by the
    template's ``_renderOHLCChart`` (flagged via ``chart_data._ohlc``). The
    chartjs-chart-financial plugin was removed because it forced a ``time``
    x-scale that required a date adapter — without it the chart rendered
    blank. The vanilla renderer draws candle BODIES as floating bars
    ``[min(o,c), max(o,c)]`` and WICKS via an inline plugin, all on a plain
    category axis. See ``cotacao.py`` docstring + ``dashboard.html``.

    [v2] The Volume Diário chart now overlays the close PRICE on a right-hand
    axis (dual axis) so volume spikes can be read alongside price action.

    Args:
        ticker: PETR4
        ohlcv:  list of {date, open, high, low, close, volume} sorted oldest-first
        ma20/50/100/200: SMA series aligned with ohlcv (None for warmup period)

    Returns:
        Two sections: OHLC candlestick (with MA overlays + range selector) and
        volume bars with a dual-axis price line.
    """
    if not ohlcv:
        return [{
            "type": "text",
            "title": f"Cotação — {ticker}",
            "text": "Sem dados de preço disponíveis.",
        }]

    dates = [p["date"] for p in ohlcv]
    closes = [p["close"] for p in ohlcv]
    volumes = [p.get("volume") or 0.0 for p in ohlcv]

    # OHLC payload for the wick plugin + scriptable body colors.
    ohlc_data = [
        {"o": p.get("open"), "h": p.get("high"), "l": p.get("low"), "c": p.get("close")}
        for p in ohlcv
    ]
    # Candle BODY as a floating bar [bodyLow, bodyHigh] = [min(o,c), max(o,c)].
    # The template renderer derives up/down colors from chart._ohlc, so we do
    # not need to send a per-point color array (which would also need slicing
    # on range-filter).
    body_data = [
        [min(p.get("open") or 0, p.get("close") or 0),
         max(p.get("open") or 0, p.get("close") or 0)]
        for p in ohlcv
    ]

    ma_datasets = [
        _ma_dataset("MA20", ma20, _MA_COLORS["MA20"]),
        _ma_dataset("MA50", ma50, _MA_COLORS["MA50"]),
        _ma_dataset("MA100", ma100, _MA_COLORS["MA100"]),
        _ma_dataset("MA200", ma200, _MA_COLORS["MA200"]),
    ]

    # ── OHLC candlestick chart (vanilla; body bars + MA overlays) ──────────
    candlestick_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Candlestick — {ticker}",
        "description": (
            "Candlestick com MM20/50/100/200. Verde = dia de alta (fechamento ≥ "
            "abertura); vermelho = dia de baixa. Use os botões para filtrar por janela."
        ),
        "chart_data": {
            # _ohlc flag routes this through _renderOHLCChart in the template.
            "_ohlc": True,
            "_ohlc_data": ohlc_data,
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "bar",
                        "label": ticker,
                        "data": body_data,
                    },
                    *ma_datasets,
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "position": "left",
                        "title": {"display": True, "text": "Preço (R$)"},
                    },
                },
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
        # Range-selector full data — MUST mirror chart_data.data.datasets order
        # so filterPriceChart keeps every series aligned: [body, MA20, MA50,
        # MA100, MA200].
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": body_data, "label": ticker},
            {"data": ma20, "label": "MA20"},
            {"data": ma50, "label": "MA50"},
            {"data": ma100, "label": "MA100"},
            {"data": ma200, "label": "MA200"},
        ],
        "price_full_data": closes,
        # OHLC wick array — sliced in lock-step with labels by filterPriceChart.
        "price_full_ohlc": ohlc_data,
    }

    # ── Volume bars + dual-axis price line ─────────────────────────────────
    # Volume bar colors (per-day): green if close >= open, red otherwise.
    vol_colors = [
        _COLOR_UP if (p.get("close") or 0) >= (p.get("open") or 0) else _COLOR_DOWN
        for p in ohlcv
    ]
    price_line = {
        "type": "line",
        "label": f"{ticker} — Preço",
        "data": closes,
        "borderColor": _PRICE_COLOR,
        "borderWidth": 1.2,
        "pointRadius": 0,
        "pointHoverRadius": 3,
        "tension": 0,
        "fill": False,
        "yAxisID": "y1",  # right-hand price axis (dual axis)
    }

    volume_section: dict[str, Any] = {
        "type": "chart",
        "title": "Volume Diário",
        "description": (
            "Volume financeiro diário (R$, eixo esquerdo). Verde: dia de alta; "
            "vermelho: dia de baixa. Linha teal: preço de fechamento (eixo direito)."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "bar",
                        "label": "Volume (R$)",
                        "data": volumes,
                        "backgroundColor": vol_colors,
                        "borderColor": vol_colors,
                        "borderWidth": 0,
                        "order": 2,
                    },
                    price_line,
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "position": "left",
                        "title": {"display": True, "text": "Volume (R$)"},
                    },
                    "y1": {
                        "position": "right",
                        "title": {"display": True, "text": "Preço (R$)"},
                        "grid": {"drawOnChartArea": False},
                    },
                },
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
        # price_full_datasets mirrors chart_data.data.datasets order:
        # [volume, price].
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": volumes, "label": "Volume (R$)"},
            {"data": closes, "label": f"{ticker} — Preço"},
        ],
        "price_full_data": volumes,
    }

    return [candlestick_section, volume_section]
