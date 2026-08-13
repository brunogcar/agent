"""skills/b3/price/report/retornos.py -- Retornos tab builder.

Cumulative return chart + drawdown chart + total return KPI + max drawdown KPI.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_pct, _is_missing


def build_retornos_sections(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
    cum_returns: list[float | None],
    drawdowns: list[float | None],
) -> list[dict]:
    """Build the Retornos tab: cumulative return + drawdown + KPIs.

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings
        closes:       daily close prices (for reference)
        cum_returns:  cumulative return from first close (fraction, e.g. 0.15 = +15%)
        drawdowns:    drawdown from running peak (negative fraction, 0 = at peak)

    Returns:
        Three sections: cumulative-return chart + drawdown chart + KPI table.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Retornos — {ticker}",
            "text": "Sem dados de preço para calcular retornos.",
        }]

    # [v2] Price line reused on both charts as a dual-axis overlay (right axis)
    # so returns/drawdown can be read alongside the underlying price level.
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

    # ── Cumulative return chart (+ dual-axis price line) ───────────────────
    cum_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Retorno Cumulativo — {ticker}",
        "description": (
            "Retorno percentual acumulado desde o primeiro dia do período (eixo "
            "esquerdo, %). Linha teal: preço de fechamento (eixo direito)."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": f"{ticker} — Retorno Cumulativo",
                        "data": cum_returns,
                        "borderColor": "#0d9488",
                        "backgroundColor": "rgba(13,148,136,0.1)",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": True,
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
                        "title": {"display": True, "text": "Retorno cumulativo (%)"},
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
        # [cum_return, price].
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": cum_returns, "label": "Retorno Cum."},
            {"data": closes, "label": f"{ticker} — Preço"},
        ],
        "price_full_data": cum_returns,
    }

    # ── Drawdown chart (always ≤ 0; red fill + dual-axis price line) ───────
    dd_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Drawdown — {ticker}",
        "description": (
            "Queda do pico de preço mais recente (peak-to-trough, eixo esquerdo). "
            "0% = no novo máximo; -30% = 30% abaixo do pico. Linha teal: preço de "
            "fechamento (eixo direito)."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Drawdown",
                        "data": drawdowns,
                        "borderColor": "#ef4444",
                        "backgroundColor": "rgba(239,68,68,0.15)",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": "origin",
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
                        "title": {"display": True, "text": "Drawdown (%)"},
                        # Drawdowns are always ≤ 0.
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
        # [drawdown, price].
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": drawdowns, "label": "Drawdown"},
            {"data": closes, "label": f"{ticker} — Preço"},
        ],
        "price_full_data": drawdowns,
    }

    # ── KPI table: total return + max drawdown + period days ───────────────
    valid_cum = [c for c in cum_returns if not _is_missing(c)]
    total_return = valid_cum[-1] if valid_cum else None
    valid_dd = [d for d in drawdowns if not _is_missing(d)]
    max_dd = min(valid_dd) if valid_dd else None

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": "Resumo de Performance",
        "columns": ["Métrica", "Valor"],
        "rows": [
            ["Retorno Cumulativo Total", fmt_pct(total_return or 0)],
            ["Drawdown Máximo",         fmt_pct(max_dd or 0)],
            ["Dias no Período",         str(len(dates))],
        ],
    }

    return [cum_section, dd_section, kpi_section]
