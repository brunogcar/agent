"""skills/b3/price/report/volatilidade.py -- Volatilidade tab builder.

Rolling volatility chart (20D/60D/252D annualized) + Bollinger Bands chart.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_pct, _is_missing


def build_volatilidade_sections(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
    vol_20d: list[float | None],
    vol_60d: list[float | None],
    vol_252d: list[float | None],
    bb_upper: list[float | None],
    bb_middle: list[float | None],
    bb_lower: list[float | None],
) -> list[dict]:
    """Build the Volatilidade tab: rolling vol + Bollinger Bands.

    Args:
        ticker:    PETR4
        dates:     list of YYYY-MM-DD strings
        closes:    daily close prices (for the BB chart)
        vol_20d:   20-day rolling annualized volatility (fraction, 0.25 = 25%)
        vol_60d:   60-day rolling annualized volatility
        vol_252d:  252-day rolling annualized volatility
        bb_upper/middle/lower: Bollinger Bands (period=20, 2σ)

    Returns:
        Two sections: rolling-volatility line chart + Bollinger Bands chart.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Volatilidade",
            "text": "Sem dados para calcular volatilidade.",
        }]

    # [v2] Price line reused as a dual-axis overlay (right axis) so volatility
    # regimes can be read alongside the underlying price level.
    _PRICE_COLOR = "#0d9488"  # teal
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

    # ── Rolling volatility chart (3 lines: 20D/60D/252D + dual-axis price) ─
    vol_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Volatilidade Anualizada",
        "description": (
            "Desvio-padrão dos retornos diários em janelas rolantes de 20/60/252 dias, "
            "anualizado por √252 (eixo esquerdo). 20D = ruído de curto prazo; 252D = "
            "volatilidade estrutural de longo prazo. Linha teal: preço de fechamento "
            "(eixo direito)."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Vol 20D (1M)",
                        "data": vol_20d,
                        "borderColor": "#facc15",
                        "borderWidth": 1.2,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "Vol 60D (3M)",
                        "data": vol_60d,
                        "borderColor": "#fb923c",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "Vol 252D (1A)",
                        "data": vol_252d,
                        "borderColor": "#ef4444",
                        "borderWidth": 2.0,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
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
                        "title": {"display": True, "text": "Volatilidade anualizada"},
                    },
                    "y1": {
                        "position": "right",
                        "title": {"display": True, "text": "Preço (R$)"},
                        "grid": {"drawOnChartArea": False},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        # price_full_datasets mirrors chart_data.data.datasets order:
        # [vol20, vol60, vol252, price].
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": vol_20d, "label": "Vol 20D"},
            {"data": vol_60d, "label": "Vol 60D"},
            {"data": vol_252d, "label": "Vol 252D"},
            {"data": closes, "label": f"{ticker} — Preço"},
        ],
        "price_full_data": vol_20d,
    }

    # ── Bollinger Bands chart (price + upper/middle/lower) ─────────────────
    bb_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Bandas de Bollinger",
        "description": (
            "MM20 (média) ± 2 desvios-padrão. Banda estreita = baixa volatilidade "
            "(possível consolidação). Preço tocando banda superior/inferior = "
            "possível sobrecompra/sobrevenda."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Banda Superior",
                        "data": bb_upper,
                        "borderColor": "#ef4444",
                        "borderWidth": 1,
                        "pointRadius": 0,
                        "tension": 0.1,
                        "fill": "+1",
                        "backgroundColor": "rgba(239,68,68,0.06)",
                    },
                    {
                        "type": "line",
                        "label": "MM20 (média)",
                        "data": bb_middle,
                        "borderColor": "#64748b",
                        "borderWidth": 1,
                        "borderDash": [4, 4],
                        "pointRadius": 0,
                        "tension": 0.1,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "Banda Inferior",
                        "data": bb_lower,
                        "borderColor": "#22c55e",
                        "borderWidth": 1,
                        "pointRadius": 0,
                        "tension": 0.1,
                        "fill": False,
                        "backgroundColor": "rgba(34,197,94,0.06)",
                    },
                    {
                        "type": "line",
                        "label": f"{ticker} — Fechamento",
                        "data": closes,
                        "borderColor": "#0d9488",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": False,
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
        # [v2] MUST mirror chart_data.data.datasets order (upper, middle, lower,
        # close) so filterPriceChart keeps every band + the price line aligned.
        "price_full_datasets": [
            {"data": bb_upper, "label": "Banda Superior"},
            {"data": bb_middle, "label": "MM20"},
            {"data": bb_lower, "label": "Banda Inferior"},
            {"data": closes, "label": f"{ticker} — Fechamento"},
        ],
        "price_full_data": closes,
    }

    # ── Latest-vol KPI table ───────────────────────────────────────────────
    def _last(seq):
        for v in reversed(seq):
            if not _is_missing(v):
                return v
        return None

    v20 = _last(vol_20d)
    v60 = _last(vol_60d)
    v252 = _last(vol_252d)

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": "Volatilidade Atual",
        "columns": ["Janela", "Volatilidade Anualizada"],
        "rows": [
            ["20D (1M)",  fmt_pct(v20 or 0)],
            ["60D (3M)",  fmt_pct(v60 or 0)],
            ["252D (1A)", fmt_pct(v252 or 0)],
        ],
    }

    # [v7] Volatilidade Atual moved to TOP. Charts after.
    return [kpi_section, vol_section, bb_section]
