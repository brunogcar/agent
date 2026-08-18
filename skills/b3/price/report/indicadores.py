"""skills/b3/price/report/indicadores.py -- Indicadores tab builder (v1.6).

Builds a reference price chart + 4 collapsible momentum oscillator charts
+ (v1.6) 3 trend/cyclical charts + a signals summary table:
  0. Preço (reference)  — single-axis close-price line chart (just for reference)
  1. RSI (14)           — line 0-100 with 30/70 reference lines
  2. MACD (12/26/9)     — histogram bars + MACD/signal lines
  3. Stochastic        — %K + %D lines 0-100 with 20/80 reference lines
  4. OBV               — cumulative signed volume line
  5. ADX (14)          — [v1.6] trend strength 0-100 with 25 reference line
  6. CCI (20)          — [v1.6] cyclical oscillator with +/-100 reference lines
  7. Williams %R (14)  — [v1.6] momentum 0 to -100 with -20/-80 reference lines
  8. Signals table     — 1-row summary of latest reading per indicator

[v1.2-v2] The dual-axis price overlay was removed from the 4 indicator
charts (was cluttering the read). A single price line chart at the TOP of
the tab serves as a reference — the user can look at it once, then scroll
through the indicators. The 4 indicator charts are collapsible (click the
title to expand/collapse) so the tab isn't visually overwhelming.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import _is_missing


# Shared colors (match the existing price-skill palette).
_COLOR_BLUE = "#3b82f6"
_COLOR_ORANGE = "#f59e0b"
_COLOR_GREEN = "#22c55e"
_COLOR_RED = "#ef4444"
_COLOR_PURPLE = "#a855f7"
_COLOR_TEAL = "#0d9488"


def _last(seq: list[float | None]) -> float | None:
    """Return the last non-None value in seq, or None."""
    for v in reversed(seq):
        if not _is_missing(v):
            return v
    return None


def _constant_line(value: float, label: str, color: str, n: int) -> dict:
    """Build a dashed horizontal reference line at ``value`` (length ``n``)."""
    return {
        "type": "line",
        "label": label,
        "data": [value] * n,
        "borderColor": color,
        "borderWidth": 1,
        "borderDash": [4, 4],
        "pointRadius": 0,
        "fill": False,
        "tension": 0,
    }


def build_indicadores_sections(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
    highs: list[float | None],
    lows: list[float | None],
    volumes: list[float | None],
    rsi: list[float | None],
    macd_line: list[float | None],
    signal_line: list[float | None],
    histogram: list[float | None],
    k_line: list[float | None],
    d_line: list[float | None],
    obv: list[float | None],
    adx: list[float | None] | None = None,
    cci: list[float | None] | None = None,
    williams_r: list[float | None] | None = None,
) -> list[dict]:
    """Build the Indicadores tab: price reference + 4 collapsible indicator charts + signals table.

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings
        closes:       daily close prices (for the reference price chart at the top)
        highs:        daily highs (used by Stochastic — passed for completeness)
        lows:         daily lows (used by Stochastic — passed for completeness)
        volumes:      daily volumes (used by OBV — passed for completeness)
        rsi:          RSI(14) series (0-100, None for warmup)
        macd_line:    MACD line (EMA12 - EMA26)
        signal_line:  MACD signal line (EMA9 of MACD)
        histogram:    MACD histogram (macd - signal)
        k_line:       Stochastic %K (0-100)
        d_line:       Stochastic %D (SMA3 of %K)
        obv:          On-Balance Volume cumulative series
        adx:          [v1.6] ADX(14) trend-strength series (0-100, None warmup)
        cci:          [v1.6] CCI(20) cyclical oscillator series
        williams_r:   [v1.6] Williams %R(14) momentum series (0 to -100)

    Returns:
        Up to nine sections: price reference chart + RSI chart + MACD chart +
        Stochastic chart + OBV chart + (v1.6) ADX + CCI + Williams %R charts
        + signals summary table. The v1.6 charts are added only when the
        corresponding series is provided (non-None).

    [v1.2-v2] The 4 indicator charts are single-axis (no dual-axis price
    overlay — was cluttering the read). A separate price reference chart
    at the top serves the same purpose. The 4 indicator charts are
    collapsible via the ``collapsible: True`` flag (the template wraps
    them in a collapsible div with the chart title as the header).
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Indicadores — {ticker}",
            "text": "Sem dados para calcular indicadores.",
        }]

    n = len(dates)

    # ── 0. Price reference chart (single axis, just for reference) ───────────
    # Placed at the TOP so the user can see the price action once, then
    # scroll through the indicators below. NOT collapsible (always visible).
    price_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"Preço — {ticker}",
        "description": (
            "Preço de fechamento diário (referência). Os indicadores abaixo "
            "usam esta série — consulte este gráfico ao ler cada oscilador."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": f"{ticker} — Fechamento",
                        "data": closes,
                        "borderColor": _COLOR_TEAL,
                        "backgroundColor": "rgba(13,148,136,0.06)",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": True,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": "Preço (R$)"}},
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": closes, "label": f"{ticker} — Fechamento"},
        ],
        "price_full_data": closes,
    }

    # ── 1. RSI chart (line 0-100 + 30/70 dashed lines, single axis) ────────
    rsi_70 = _constant_line(70.0, "Sobrecompra (70)", _COLOR_RED, n)
    rsi_30 = _constant_line(30.0, "Sobrevenda (30)", _COLOR_GREEN, n)
    rsi_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"RSI (14) — {ticker}",
        "description": (
            "Índice de Força Relativa (RSI, 14 períodos). Acima de 70 = "
            "sobrecompra (possível correção). Abaixo de 30 = sobrevenda "
            "(possível repique)."
        ),
        "collapsible": True,
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "RSI (14)",
                        "data": rsi,
                        "borderColor": _COLOR_BLUE,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                    },
                    rsi_70,
                    rsi_30,
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "min": 0,
                        "max": 100,
                        "title": {"display": True, "text": "RSI (0-100)"},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": rsi, "label": "RSI (14)"},
            {"data": [70.0] * n, "label": "Sobrecompra (70)"},
            {"data": [30.0] * n, "label": "Sobrevenda (30)"},
        ],
        "price_full_data": rsi,
    }

    # ── 2. MACD chart (histogram bars + MACD/signal lines, single axis) ─────
    hist_colors = [
        _COLOR_GREEN if (not _is_missing(h) and h >= 0) else _COLOR_RED
        for h in histogram
    ]
    macd_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"MACD (12/26/9) — {ticker}",
        "description": (
            "Convergência/Divergência de Médias Móveis. Linha azul = MACD "
            "(EMA12 − EMA26). Linha laranja = sinal (EMA9 do MACD). Barras "
            "= histograma (MACD − sinal): verde = momentum de alta; "
            "vermelho = momentum de baixa. Cruzamento de alta: MACD cruza "
            "acima do sinal."
        ),
        "collapsible": True,
        "chart_data": {
            "type": "bar",  # mixed chart — bar base, line datasets override
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "bar",
                        "label": "Histograma",
                        "data": histogram,
                        "backgroundColor": hist_colors,
                        "borderColor": hist_colors,
                        "borderWidth": 0,
                        "order": 3,
                    },
                    {
                        "type": "line",
                        "label": "MACD (12/26)",
                        "data": macd_line,
                        "borderColor": _COLOR_BLUE,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                        "order": 2,
                    },
                    {
                        "type": "line",
                        "label": "Sinal (9)",
                        "data": signal_line,
                        "borderColor": _COLOR_ORANGE,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                        "order": 1,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "title": {"display": True, "text": "MACD / Sinal / Histograma"},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": histogram, "label": "Histograma"},
            {"data": macd_line, "label": "MACD (12/26)"},
            {"data": signal_line, "label": "Sinal (9)"},
        ],
        "price_full_data": macd_line,
    }

    # ── 3. Stochastic chart (%K + %D + 20/80 dashed, single axis) ───────────
    stoch_80 = _constant_line(80.0, "Sobrecompra (80)", _COLOR_RED, n)
    stoch_20 = _constant_line(20.0, "Sobrevenda (20)", _COLOR_GREEN, n)
    stoch_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"Stochastic (14/3/3) — {ticker}",
        "description": (
            "Oscilador Estocástico. %K = (close − mínima_14) / (máxima_14 − "
            "mínima_14) × 100. %D = SMA3 do %K. Acima de 80 = sobrecompra; "
            "abaixo de 20 = sobrevenda. Cruzamento de %K acima de %D = sinal "
            "de compra."
        ),
        "collapsible": True,
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "%K (14)",
                        "data": k_line,
                        "borderColor": _COLOR_BLUE,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "%D (3)",
                        "data": d_line,
                        "borderColor": _COLOR_ORANGE,
                        "borderWidth": 1.5,
                        "borderDash": [2, 2],
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                    },
                    stoch_80,
                    stoch_20,
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "min": 0,
                        "max": 100,
                        "title": {"display": True, "text": "%K / %D (0-100)"},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": k_line, "label": "%K (14)"},
            {"data": d_line, "label": "%D (3)"},
            {"data": [80.0] * n, "label": "Sobrecompra (80)"},
            {"data": [20.0] * n, "label": "Sobrevenda (20)"},
        ],
        "price_full_data": k_line,
    }

    # ── 4. OBV chart (cumulative signed volume, single axis) ────────────────
    obv_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"On-Balance Volume (OBV) — {ticker}",
        "description": (
            "Volume acumulado assinado pela direção do preço: +volume em dias "
            "de alta, −volume em dias de baixa. OBV subindo com preço = "
            "tendência saudável (volume confirma). OBV caindo com preço "
            "subindo = divergência bearish (rally sem força)."
        ),
        "collapsible": True,
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "OBV",
                        "data": obv,
                        "borderColor": _COLOR_PURPLE,
                        "backgroundColor": "rgba(168,85,247,0.08)",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": True,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {
                        "title": {"display": True, "text": "OBV (cumulativo)"},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": obv, "label": "OBV"},
        ],
        "price_full_data": obv,
    }

    # ── 5. ADX chart (v1.6) — trend strength 0-100 + 25 reference line ────
    adx_sections: list[dict] = []
    if adx is not None:
        adx_25 = _constant_line(25.0, "Tendencia forte (25)", _COLOR_ORANGE, n)
        adx_75 = _constant_line(75.0, "Tendencia muito forte (75)", _COLOR_RED, n)
        adx_chart: dict[str, Any] = {
            "type": "chart",
            "title": f"ADX (14) — {ticker}",
            "description": (
                "Average Directional Index (14 periodos). Mede a FORCA da "
                "tendencia (0-100), nao a direcao. ADX > 25 = tendencia forte "
                "(alta ou baixa); ADX < 20 = sem tendencia definida (lateral). "
                "Usa Wilder smoothing (mesma recursao do RSI). Complementa o "
                "MACD (que mostra direcao + momentum)."
            ),
            "collapsible": True,
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [
                        {
                            "type": "line",
                            "label": "ADX (14)",
                            "data": adx,
                            "borderColor": _COLOR_TEAL,
                            "borderWidth": 1.5,
                            "pointRadius": 0,
                            "pointHoverRadius": 3,
                            "tension": 0.2,
                            "fill": False,
                        },
                        adx_25,
                        adx_75,
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "index", "intersect": False},
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 12}},
                        "y": {
                            "min": 0,
                            "max": 100,
                            "title": {"display": True, "text": "ADX (0-100)"},
                        },
                    },
                    "plugins": {"legend": {"display": True, "position": "top"}},
                },
            },
            "price_range_selector": True,
            "price_full_labels": dates,
            "price_full_datasets": [
                {"data": adx, "label": "ADX (14)"},
                {"data": [25.0] * n, "label": "Tendencia forte (25)"},
                {"data": [75.0] * n, "label": "Tendencia muito forte (75)"},
            ],
            "price_full_data": adx,
        }
        adx_sections.append(adx_chart)

    # ── 6. CCI chart (v1.6) — cyclical oscillator with +/-100 reference ───
    if cci is not None:
        cci_p100 = _constant_line(100.0, "Sobrecompra (+100)", _COLOR_RED, n)
        cci_n100 = _constant_line(-100.0, "Sobrevenda (-100)", _COLOR_GREEN, n)
        cci_chart: dict[str, Any] = {
            "type": "chart",
            "title": f"CCI (20) — {ticker}",
            "description": (
                "Commodity Channel Index (20 periodos). Mede o desvio do "
                "preco tipico (H+L+C)/3 da sua media, normalizado pelo desvio "
                "medio. CCI > +100 = sobrecompra; CCI < -100 = sobrevenda. "
                "Captura ciclos diferentes do RSI/Stochastic."
            ),
            "collapsible": True,
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [
                        {
                            "type": "line",
                            "label": "CCI (20)",
                            "data": cci,
                            "borderColor": _COLOR_PURPLE,
                            "borderWidth": 1.5,
                            "pointRadius": 0,
                            "pointHoverRadius": 3,
                            "tension": 0.2,
                            "fill": False,
                        },
                        cci_p100,
                        cci_n100,
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "index", "intersect": False},
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 12}},
                        "y": {
                            "title": {"display": True, "text": "CCI"},
                        },
                    },
                    "plugins": {"legend": {"display": True, "position": "top"}},
                },
            },
            "price_range_selector": True,
            "price_full_labels": dates,
            "price_full_datasets": [
                {"data": cci, "label": "CCI (20)"},
                {"data": [100.0] * n, "label": "Sobrecompra (+100)"},
                {"data": [-100.0] * n, "label": "Sobrevenda (-100)"},
            ],
            "price_full_data": cci,
        }
        adx_sections.append(cci_chart)

    # ── 7. Williams %R chart (v1.6) — momentum 0 to -100 ──────────────────
    if williams_r is not None:
        wr_n20 = _constant_line(-20.0, "Sobrecompra (-20)", _COLOR_RED, n)
        wr_n80 = _constant_line(-80.0, "Sobrevenda (-80)", _COLOR_GREEN, n)
        wr_chart: dict[str, Any] = {
            "type": "chart",
            "title": f"Williams %R (14) — {ticker}",
            "description": (
                "Williams %R (14 periodos). Oscilador de momentum 0 a -100. "
                "%R > -20 (prox. de 0) = sobrecompra; %R < -80 (prox. de -100) "
                "= sobrevenda. Matematicamente equivalente ao %K invertido "
                "(Stochastic) mas com escala e convencao diferentes."
            ),
            "collapsible": True,
            "chart_data": {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [
                        {
                            "type": "line",
                            "label": "Williams %R (14)",
                            "data": williams_r,
                            "borderColor": _COLOR_BLUE,
                            "borderWidth": 1.5,
                            "pointRadius": 0,
                            "pointHoverRadius": 3,
                            "tension": 0.2,
                            "fill": False,
                        },
                        wr_n20,
                        wr_n80,
                    ],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "index", "intersect": False},
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 12}},
                        "y": {
                            "min": -100,
                            "max": 0,
                            "title": {"display": True, "text": "Williams %R (0 a -100)"},
                        },
                    },
                    "plugins": {"legend": {"display": True, "position": "top"}},
                },
            },
            "price_range_selector": True,
            "price_full_labels": dates,
            "price_full_datasets": [
                {"data": williams_r, "label": "Williams %R (14)"},
                {"data": [-20.0] * n, "label": "Sobrecompra (-20)"},
                {"data": [-80.0] * n, "label": "Sobrevenda (-80)"},
            ],
            "price_full_data": williams_r,
        }
        adx_sections.append(wr_chart)

    # ── 8. Signals summary table ────────────────────────────────────────────
    rsi_val = _last(rsi)
    hist_val = _last(histogram)
    k_val = _last(k_line)
    obv_val = _last(obv)
    obv_prior = obv[-21] if len(obv) >= 21 else None
    obv_trend = None
    if obv_val is not None and obv_prior is not None:
        obv_trend = obv_val - obv_prior

    def _rsi_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v >= 70:
            return "Sobrecompra (≥70)"
        if v <= 30:
            return "Sobrevenda (≤30)"
        return "Neutro"

    def _macd_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v > 0:
            return "Alta (hist > 0)"
        if v < 0:
            return "Baixa (hist < 0)"
        return "Neutro"

    def _stoch_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v >= 80:
            return "Sobrecompra (≥80)"
        if v <= 20:
            return "Sobrevenda (≤20)"
        return "Neutro"

    def _obv_signal(trend: float | None) -> str:
        if trend is None:
            return "—"
        if trend > 0:
            return "Alta (acumulando)"
        if trend < 0:
            return "Baixa (distribuindo)"
        return "Neutro"

    def _adx_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v >= 25:
            return "Tendencia forte (≥25)"
        if v < 20:
            return "Sem tendencia (<20)"
        return "Tendencia moderada"

    def _cci_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v > 100:
            return "Sobrecompra (>+100)"
        if v < -100:
            return "Sobrevenda (<-100)"
        return "Neutro"

    def _wr_signal(v: float | None) -> str:
        if v is None:
            return "—"
        if v > -20:
            return "Sobrecompra (>-20)"
        if v < -80:
            return "Sobrevenda (<-80)"
        return "Neutro"

    def _fmt(v: float | None, digits: int = 2) -> str:
        if v is None:
            return "—"
        return f"{v:.{digits}f}"

    adx_val = _last(adx) if adx is not None else None
    cci_val = _last(cci) if cci is not None else None
    wr_val  = _last(williams_r) if williams_r is not None else None

    signals_rows = [
        ["RSI (14)",           _fmt(rsi_val),      _rsi_signal(rsi_val)],
        ["MACD (histograma)",  _fmt(hist_val),     _macd_signal(hist_val)],
        ["Stochastic %K (14)", _fmt(k_val),        _stoch_signal(k_val)],
        ["OBV (20D trend)",    _fmt(obv_trend, 0), _obv_signal(obv_trend)],
    ]
    if adx is not None:
        signals_rows.append(["ADX (14)",        _fmt(adx_val), _adx_signal(adx_val)])
    if cci is not None:
        signals_rows.append(["CCI (20)",        _fmt(cci_val), _cci_signal(cci_val)])
    if williams_r is not None:
        signals_rows.append(["Williams %R (14)", _fmt(wr_val),  _wr_signal(wr_val)])

    signals_table: dict[str, Any] = {
        "type": "table",
        "title": "Sinais Atuais",
        "description": (
            "Classificação da última leitura de cada indicador. "
            "Sobrecompra = possível correção de baixa; Sobrevenda = "
            "possível repique de alta. Sinais conflitantes (ex.: RSI "
            "sobrecomprado + MACD de alta) sugerem aguardar confirmação."
        ),
        "columns": ["Indicador", "Valor Atual", "Sinal"],
        "rows": signals_rows,
        # Right-align the "Valor Atual" column (index 1); left-align the
        # "Indicador" name (0) and the "Sinal" classifier (2).
        "column_align": ["left", "right", "left"],
        "note": (
            "Sinais são leituras pontuais — NÃO são recomendações de "
            "compra/venda. Sempre confirme com a ação do preço + contexto "
            "de mercado. Sobrecompra pode persistir em tendências fortes."
        ),
    }

    return [price_chart, rsi_chart, macd_chart, stoch_chart, obv_chart] + adx_sections + [signals_table]
