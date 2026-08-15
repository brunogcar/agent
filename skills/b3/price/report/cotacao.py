"""skills/cotacao.py -- Cotação tab builders (v1.4).

Builds the Cotação tab: candlestick chart + price snapshot table + multi-period
returns table + annual returns table + price histogram (heatmap) + Início vs
Fim annual chart. The Volume Diário chart was removed in v1.4 (the Volume tab
already covers it).

[v1.4] New sections:
  - Price snapshot table (mirrors the user's spreadsheet row 5)
  - Multi-period performance table (Dia / Semana / ... / 20 anos)
  - Annual returns table (per-year Início / Fim / %)
  - Price histogram with heatmap colors (blue→yellow→red by frequency)
  - Início vs Fim annual line chart (with data labels via inline plugin)

Negative values in tables are colored red via the ``negative_red`` flag on
the section dict (handled by the data_table macro).
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
    """Build 6 KPI cards for the Cotação tab (unchanged from v1.0)."""
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

    if prev_close and prev_close > 0 and not _is_missing(close):
        var_pct = (close - prev_close) / prev_close
        var_str = fmt_pct(var_pct)
        delta = ("+" if var_pct >= 0 else "") + var_str
    else:
        var_str = "—"
        delta = None

    sub_52w = ""
    if range_52w and range_52w.get("high_52w") and range_52w.get("low_52w"):
        sub_52w = (
            f"52s: {fmt_brl(range_52w['low_52w'], suffix=False)} – "
            f"{fmt_brl(range_52w['high_52w'], suffix=False)}"
        )

    return [
        {"type": "kpi", "label": "Preço",          "value": fmt_brl(close, suffix=False), "unit": "", "subtitle": qdate, "delta": delta},
        {"type": "kpi", "label": "Variação (dia)", "value": var_str, "unit": "", "subtitle": "vs. fechamento anterior"},
        {"type": "kpi", "label": "Abertura",       "value": fmt_brl(open_, suffix=False), "unit": "", "subtitle": ""},
        {"type": "kpi", "label": "Máxima",         "value": fmt_brl(high, suffix=False), "unit": "", "subtitle": sub_52w},
        {"type": "kpi", "label": "Mínima",         "value": fmt_brl(low, suffix=False), "unit": "", "subtitle": ""},
        {"type": "kpi", "label": "Volume",         "value": fmt_brl(volume, suffix=False) if volume else "—", "unit": "", "subtitle": f"{quote.get('trade_count') or 0} negócios"},
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
    """Build the Cotação tab: candlestick + 3 tables + 2 charts (v1.4).

    [v1.4] The Volume Diário chart was removed (the Volume tab covers it).
    Added: price snapshot table, multi-period returns table, annual returns
    table, price histogram (heatmap), Início vs Fim annual chart.

    Args:
        ticker: PETR4
        ohlcv:  list of {date, open, high, low, close, volume} sorted oldest-first
        ma20/50/100/200: SMA series aligned with ohlcv (None for warmup period)
        snapshot:       [v1.4] compute_price_snapshot result (or None)
        period_returns: [v1.4] compute_period_returns result (or None)
        annual_returns: [v1.4] compute_annual_returns result (or None)
        histogram:      [v1.4] compute_price_histogram result (or None)

    Returns:
        List of sections (candlestick + snapshot table + period returns
        table + annual returns table + histogram chart + inicio-fin chart).
    """
    if not ohlcv:
        return [{
            "type": "text",
            "title": f"Cotação — {ticker}",
            "text": "Sem dados de preço disponíveis.",
        }]

    sections: list[dict] = []
    dates = [p["date"] for p in ohlcv]
    closes = [p["close"] for p in ohlcv]

    # ── 1. Candlestick chart (with MA overlays + range selector) ────────────
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
        "title": f"Candlestick — {ticker}",
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

    # ── 2. Price snapshot table (v1.4) ─────────────────────────────────────
    if snapshot:
        snap = snapshot
        # Format each value; negative values will be colored red via negative_red.
        def _fmt_signed_brl(v):
            if v is None or _is_missing(v):
                return "—"
            s = fmt_brl(v, suffix=False)
            return ("+" if v >= 0 else "") + s if v >= 0 else s
        def _fmt_signed_pct(v):
            if v is None or _is_missing(v):
                return "—"
            s = fmt_pct(v)
            return ("+" if v >= 0 else "") + s if v >= 0 else s
        snap_rows = [
            ["Fechamento Anterior",  _fmt_signed_brl(snap.get("prior_close"))],
            ["Abertura",              _fmt_signed_brl(snap.get("open"))],
            ["Atual",                _fmt_signed_brl(snap.get("current"))],
            ["Variação (dia)",       _fmt_signed_brl(snap.get("daily_diff")) + " (" + _fmt_signed_pct(snap.get("daily_pct")) + ")"],
            ["Mínima (dia)",         _fmt_signed_brl(snap.get("intraday_low"))],
            ["Máxima (dia)",         _fmt_signed_brl(snap.get("intraday_high"))],
            ["Amplitude (dia)",      _fmt_signed_brl(snap.get("intraday_range")) + " (" + _fmt_signed_pct(snap.get("intraday_range_pct")) + ")"],
            ["Mínima 52s",           _fmt_signed_brl(snap.get("low_52w"))],
            ["Máxima 52s",           _fmt_signed_brl(snap.get("high_52w"))],
            ["Da Mínima 52s",        _fmt_signed_brl(snap.get("from_52w_low")) + " (" + _fmt_signed_pct(snap.get("from_52w_low_pct")) + ")"],
            ["Até a Máxima 52s",     _fmt_signed_brl(snap.get("to_52w_high")) + " (" + _fmt_signed_pct(snap.get("to_52w_high_pct")) + ")"],
        ]
        sections.append({
            "type": "table",
            "title": "Snapshot de Preço",
            "description": (
                "Resumo do último pregão + posição dentro do range de 52 semanas. "
                "Valores negativos em vermelho."
            ),
            "columns": ["Métrica", "Valor"],
            "rows": snap_rows,
            "negative_red": True,
        })

    # ── 3. Multi-period performance table (v1.4) ────────────────────────────
    if period_returns:
        pr_rows = []
        for p in period_returns:
            ret = p.get("return_pct")
            ref = p.get("reference_price")
            ret_str = ("+" + fmt_pct(ret)) if (ret is not None and ret >= 0) else (fmt_pct(ret) if ret is not None else "—")
            ref_str = fmt_brl(ref, suffix=False) if ref is not None else "—"
            pr_rows.append([p["label"], ret_str, ref_str])
        sections.append({
            "type": "table",
            "title": "Performance por Período",
            "description": (
                "Retorno percentual + preço de referência em múltiplos horizontes "
                "(dia, semana, mês, trimestre, ano, 2-20 anos). Calculado a partir "
                "do fechamento atual vs o fechamento mais próximo de N dias atrás. "
                "Valores negativos em vermelho."
            ),
            "columns": ["Período", "Retorno", "Preço de Referência"],
            "rows": pr_rows,
            "negative_red": True,
        })

    # ── 4. Annual returns table (v1.4) ──────────────────────────────────────
    if annual_returns:
        ar_rows = []
        for a in reversed(annual_returns):  # newest-first
            ret = a.get("return_pct")
            ret_str = ("+" + fmt_pct(ret)) if (ret is not None and ret >= 0) else (fmt_pct(ret) if ret is not None else "—")
            ar_rows.append([
                str(a["year"]),
                fmt_brl(a.get("inicio"), suffix=False),
                fmt_brl(a.get("fim"), suffix=False),
                ret_str,
            ])
        sections.append({
            "type": "table",
            "title": "Oscilações Anuais",
            "description": (
                "Preço de Início (primeiro pregão do ano) + Fim (último pregão) "
                "+ variação % por ano. Ano atual usa o último fechamento disponível "
                "como Fim. Valores negativos em vermelho."
            ),
            "columns": ["Ano", "Início", "Fim", "Variação"],
            "rows": ar_rows,
            "negative_red": True,
        })

    # ── 5. Price histogram with heatmap (v1.4) ─────────────────────────────
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
            "title": f"Histograma de Preço — {ticker}",
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
                    "interaction": {"mode": "index", "intersect": False},
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 15, "maxRotation": 45, "minRotation": 30},
                              "title": {"display": True, "text": "Preço (R$)"}},
                        "y": {"title": {"display": True, "text": "Frequência (pregões)"},
                              "beginAtZero": True},
                    },
                    "plugins": {"legend": {"display": True, "position": "top"}},
                },
            },
        })

    # ── 6. Início vs Fim annual chart (v1.4) ─────────────────────────────
    if annual_returns and len(annual_returns) >= 2:
        years = [str(a["year"]) for a in annual_returns]
        inicio_prices = [a.get("inicio") for a in annual_returns]
        fim_prices = [a.get("fim") for a in annual_returns]
        sections.append({
            "type": "chart",
            "title": f"Início vs Fim — {ticker}",
            "description": (
                "Preço de Início (primeiro pregão do ano, azul) + Fim (último "
                "pregão, vermelho) por ano. Ano atual usa o último fechamento "
                "disponível como Fim. Valores exibidos acima de cada ponto."
            ),
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": years,
                    "datasets": [
                        {
                            "type": "line",
                            "label": "Início",
                            "data": inicio_prices,
                            "borderColor": "#3b82f6",
                            "backgroundColor": "#3b82f6",
                            "borderWidth": 1.5,
                            "pointRadius": 4,
                            "pointHoverRadius": 6,
                            "tension": 0.2,
                            "fill": False,
                        },
                        {
                            "type": "line",
                            "label": "Fim",
                            "data": fim_prices,
                            "borderColor": "#ef4444",
                            "backgroundColor": "#ef4444",
                            "borderWidth": 1.5,
                            "pointRadius": 4,
                            "pointHoverRadius": 6,
                            "tension": 0.2,
                            "fill": False,
                        },
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "index", "intersect": False},
                    "layout": {"padding": {"top": 20}},
                    "scales": {
                        "x": {"title": {"display": True, "text": "Ano"},
                              "ticks": {"maxTicksLimit": 15}},
                        "y": {"title": {"display": True, "text": "Preço (R$)"}},
                    },
                    "plugins": {
                        "legend": {"display": True, "position": "top"},
                        # [v1.4] Inline datalabels flag — the template's
                        # _priceDatalabels plugin reads this + renders the
                        # value above each point.
                        "_datalabels": True,
                    },
                },
            },
        })

    return sections
