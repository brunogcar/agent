"""skills/cotacao.py -- Cotação tab builders (v7).

[v7] Changes:
- Snapshot: two_column with 3 columns (label, value, %), % colored green/red
- Candlestick moved BELOW the snapshot tables
- KPI: Preço (no delta), Variação ($ diff + % delta green/red), Abertura/Máxima/Mínima (price delta)
- No "+" prefix on positive values
- Volume KPI uses auto-scale (bi/mi)
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_brl, fmt_pct, _is_missing


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


def build_quote_kpis(quote: dict | None, prev_close: float | None,
                     range_52w: dict | None) -> list[dict]:
    """Build 6 KPI cards for the Cotação tab.

    [v7] Preço: no delta. Variação: value = $ diff, delta = % (green/red).
    Abertura/Máxima/Mínima: show price delta ($ diff from close).
    Volume: auto-scale (bi/mi). No "+" prefix anywhere.
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

    def _price_delta(value, reference):
        if value is None or reference is None or _is_missing(value) or _is_missing(reference):
            return None
        diff = value - reference
        return fmt_brl(diff, suffix=False)

    if prev_close and prev_close > 0 and not _is_missing(close):
        var_pct = (close - prev_close) / prev_close
        var_str = fmt_pct(var_pct)
        var_diff = close - prev_close
        var_value = fmt_brl(var_diff, suffix=False)
        var_delta = var_str
    else:
        var_value = "—"
        var_delta = None

    sub_52w = ""
    if range_52w and range_52w.get("high_52w") and range_52w.get("low_52w"):
        sub_52w = (
            f"52s: {fmt_brl(range_52w['low_52w'], suffix=False)} – "
            f"{fmt_brl(range_52w['high_52w'], suffix=False)}"
        )

    return [
        {"type": "kpi", "label": "Preço",          "value": fmt_brl(close, suffix=False), "unit": "", "subtitle": qdate},
        {"type": "kpi", "label": "Variação (dia)", "value": var_value, "unit": "", "subtitle": "vs. fechamento anterior", "delta": var_delta},
        {"type": "kpi", "label": "Abertura",       "value": fmt_brl(open_, suffix=False), "unit": "", "subtitle": "", "delta": _price_delta(open_, close)},
        {"type": "kpi", "label": "Máxima",         "value": fmt_brl(high, suffix=False), "unit": "", "subtitle": sub_52w, "delta": _price_delta(high, close)},
        {"type": "kpi", "label": "Mínima",         "value": fmt_brl(low, suffix=False), "unit": "", "subtitle": "", "delta": _price_delta(low, close)},
        {"type": "kpi", "label": "Volume",         "value": fmt_brl(volume, suffix=True) if volume else "—", "unit": "", "subtitle": f"{quote.get('trade_count') or 0} negócios"},
    ]


def build_cotacao_sections(
    ticker: str,
    ohlcv: list[dict],
    ma20: list[float | None],
    ma50: list[float | None],
    ma100: list[float | None],
    ma200: list[float | None],
    snapshot: dict | None = None,
    period_returns: list[dict] | None = None,
    annual_returns: list[dict] | None = None,
    histogram: dict | None = None,
) -> list[dict]:
    """Build the Cotação tab: snapshot tables FIRST + candlestick + charts.

    [v7] Candlestick moved BELOW the snapshot tables. Snapshot uses two_column
    with 3 columns (label, value, %). % colored green/red.
    """
    if not ohlcv:
        return [{"type": "text", "title": "Cotação", "text": "Sem dados de preço disponíveis."}]

    sections: list[dict] = []
    dates = [p["date"] for p in ohlcv]
    closes = [p["close"] for p in ohlcv]

    # ── 1. Price snapshot — 2 two_column sections (v8: % vs Atual for all) ─
    if snapshot:
        snap = snapshot
        current = snap.get("current")
        def _fmt_brl(v):
            if v is None or _is_missing(v):
                return "—"
            return fmt_brl(v, suffix=False)
        def _pct_vs_current(v):
            """% vs current price (Atual). Returns cell dict with green/red color."""
            if v is None or _is_missing(v) or current is None or current == 0:
                return "—"
            pct = (v - current) / current
            return {"text": fmt_pct(pct), "color": "#22c55e" if pct >= 0 else "#ef4444"}
        def _pct_cell(v):
            """Pre-computed % value. Returns cell dict with green/red color."""
            if v is None or _is_missing(v):
                return "—"
            return {"text": fmt_pct(v), "color": "#22c55e" if v >= 0 else "#ef4444"}

        # Geral: all values show % vs Atual
        geral_rows = [
            {"label": "Fechamento Anterior", "value": _fmt_brl(snap.get("prior_close")), "pct": _pct_vs_current(snap.get("prior_close"))},
            {"label": "Abertura", "value": _fmt_brl(snap.get("open")), "pct": _pct_vs_current(snap.get("open"))},
            {"label": "Atual", "value": _fmt_brl(current), "pct": "—"},
        ]
        # Dia: Mínima/Máxima show % vs Atual; Variação/Amplitude use pre-computed %
        dia_rows = [
            {"label": "Variação (dia)", "value": _fmt_brl(snap.get("daily_diff")), "pct": _pct_cell(snap.get("daily_pct"))},
            {"label": "Mínima (dia)", "value": _fmt_brl(snap.get("intraday_low")), "pct": _pct_vs_current(snap.get("intraday_low"))},
            {"label": "Máxima (dia)", "value": _fmt_brl(snap.get("intraday_high")), "pct": _pct_vs_current(snap.get("intraday_high"))},
            {"label": "Amplitude (dia)", "value": _fmt_brl(snap.get("intraday_range")), "pct": _pct_cell(snap.get("intraday_range_pct"))},
        ]
        sections.append({
            "type": "two_column",
            "left_title": "Geral",
            "left_rows": geral_rows,
            "right_title": "Dia",
            "right_rows": dia_rows,
            "negative_red": True,
            "positive_green": True,
        })

        # 52s: Mínima/Máxima show % vs Atual; Da Mínima/Até a Máxima use pre-computed %
        min52_rows = [
            {"label": "Mínima 52s", "value": _fmt_brl(snap.get("low_52w")), "pct": _pct_vs_current(snap.get("low_52w"))},
            {"label": "Da Mínima", "value": _fmt_brl(snap.get("from_52w_low")), "pct": _pct_cell(snap.get("from_52w_low_pct"))},
        ]
        max52_rows = [
            {"label": "Máxima 52s", "value": _fmt_brl(snap.get("high_52w")), "pct": _pct_vs_current(snap.get("high_52w"))},
            {"label": "Até a Máxima", "value": _fmt_brl(snap.get("to_52w_high")), "pct": _pct_cell(snap.get("to_52w_high_pct"))},
        ]
        sections.append({
            "type": "two_column",
            "left_title": "Range 52 Semanas — Mínima",
            "left_rows": min52_rows,
            "right_title": "Range 52 Semanas — Máxima",
            "right_rows": max52_rows,
            "negative_red": True,
            "positive_green": True,
        })

    # ── 2. Performance + Annual returns side by side (no extra % column) ──
    if period_returns and annual_returns:
        pr_rows = []
        for p in period_returns:
            ret = p.get("return_pct")
            ret_str = fmt_pct(ret) if ret is not None else "—"
            pr_rows.append({"label": p["label"], "value": ret_str})
        ar_rows = []
        for a in reversed(annual_returns):
            ret = a.get("return_pct")
            ret_str = fmt_pct(ret) if ret is not None else "—"
            ar_rows.append({"label": str(a["year"]), "value": ret_str})
        sections.append({
            "type": "two_column",
            "left_title": "Performance por Período",
            "left_rows": pr_rows,
            "right_title": "Oscilações Anuais",
            "right_rows": ar_rows,
            "negative_red": True,
            "positive_green": True,
        })

    # ── 3. Candlestick chart (moved BELOW tables in v7) ───────────────────
    ohlc_data = [
        {"o": p.get("open"), "h": p.get("high"), "l": p.get("low"), "c": p.get("close")}
        for p in ohlcv
    ]
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
    candlestick_section: dict[str, Any] = {
        "type": "chart",
        "title": "Candlestick",
        "description": (
            "Candlestick com MM20/50/100/200. Verde = dia de alta (fechamento ≥ "
            "abertura); vermelho = dia de baixa. Use os botões para filtrar por janela."
        ),
        "chart_data": {
            "_ohlc": True,
            "_ohlc_data": ohlc_data,
            "data": {
                "labels": dates,
                "datasets": [
                    {"type": "bar", "label": ticker, "data": body_data},
                    *ma_datasets,
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"position": "left", "title": {"display": True, "text": "Preço (R$)"}},
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
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
        "price_full_ohlc": ohlc_data,
    }
    sections.append(candlestick_section)

    # ── 4. Price histogram with heatmap ───────────────────────────────────
    if histogram and histogram.get("bins"):
        bins = histogram["bins"]
        hist_labels = [b["label"] for b in bins]
        hist_counts = [b["count"] for b in bins]
        hist_colors = [b["color"] for b in bins]
        poc = histogram.get("poc_label")
        va_low = histogram.get("value_area_low")
        va_high = histogram.get("value_area_high")
        total_days = histogram.get("total_days", 0)
        desc_parts = [
            f"Distribuição dos fechamentos diários em {len(bins)} bins. "
            f"Cor = heatmap (azul=baixa frequência, amarelo=média, vermelha=alta). "
            f"Total: {total_days} pregões."
        ]
        if poc:
            desc_parts.append(f" Ponto de Controle (POC): R$ {poc}.")
        if va_low is not None and va_high is not None:
            desc_parts.append(f" Área de Valor (70%): R$ {va_low:.2f} – R$ {va_high:.2f}.")
        sections.append({
            "type": "chart",
            "title": "Histograma de Preço",
            "description": "".join(desc_parts),
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": hist_labels,
                    "datasets": [{
                        "type": "bar",
                        "label": "Frequência (pregões)",
                        "data": hist_counts,
                        "backgroundColor": hist_colors,
                        "borderColor": hist_colors,
                        "borderWidth": 0,
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 20}},
                        "y": {"title": {"display": True, "text": "Pregões"}},
                    },
                    "plugins": {"legend": {"display": False}},
                },
            },
        })

    # ── 5. Início vs Fim annual chart ─────────────────────────────────────
    if annual_returns:
        years = [str(a["year"]) for a in annual_returns]
        inicio_vals = [a.get("inicio") for a in annual_returns]
        fim_vals = [a.get("fim") for a in annual_returns]
        sections.append({
            "type": "chart",
            "title": "Início vs Fim",
            "description": (
                "Preço de Início (primeiro pregão) vs Fim (último pregão) por ano. "
                "Mostra a trajetória de preço ano a ano."
            ),
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": years,
                    "datasets": [
                        {
                            "label": "Início",
                            "data": inicio_vals,
                            "borderColor": _COLOR_UP,
                            "backgroundColor": _COLOR_UP,
                            "borderWidth": 2,
                            "pointRadius": 3,
                            "tension": 0.1,
                            "fill": False,
                        },
                        {
                            "label": "Fim",
                            "data": fim_vals,
                            "borderColor": _COLOR_DOWN,
                            "backgroundColor": _COLOR_DOWN,
                            "borderWidth": 2,
                            "pointRadius": 3,
                            "tension": 0.1,
                            "fill": False,
                        },
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "x": {"title": {"display": True, "text": "Ano"}},
                        "y": {"title": {"display": True, "text": "Preço (R$)"}},
                    },
                    "plugins": {
                        "title": {"display": True, "text": "Início vs Fim"},
                        "legend": {"display": True, "position": "top"},
                    },
                },
            },
            "options": {"_datalabels": True},
        })

    return sections
