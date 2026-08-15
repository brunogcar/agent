"""skills/b3/price/report/retornos.py -- Retornos tab builder.

Cumulative return chart + drawdown chart + total return KPI + max drawdown KPI.

[v1.1] The dual-axis price overlay (right axis) was removed from both the
cumulative-return + drawdown charts — they now show ONLY the return/drawdown
series on a single left axis. The Cotacao tab's Volume Diário chart keeps
its dual-axis price overlay (volume + price is the intended pattern there).
Chart data values are multiplied by 100 so the y-axis (titled "%") matches
the displayed values (was: fractions like 0.15 shown with a "(%)" title).
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
        closes:       daily close prices (UNUSED since v1.1 — was the dual-axis
                      price overlay; kept in signature for caller compat)
        cum_returns:  cumulative return from first close (fraction, e.g. 0.15 = +15%)
        drawdowns:    drawdown from running peak (negative fraction, 0 = at peak)

    Returns:
        Three sections: cumulative-return chart + drawdown chart + KPI table.

    [v1.1] Charts display values × 100 so the y-axis "%" title matches the
    plotted data (was: raw fractions 0.15 shown with "(%)" title). The
    dual-axis price overlay was removed.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Retornos — {ticker}",
            "text": "Sem dados de preço para calcular retornos.",
        }]

    # [v1.1] Convert fractions → percentages for chart display (axis title says "%").
    cum_returns_pct = [
        (v * 100) if not _is_missing(v) else None
        for v in cum_returns
    ]
    drawdowns_pct = [
        (v * 100) if not _is_missing(v) else None
        for v in drawdowns
    ]

    # ── Cumulative return chart (single left axis, %) ─────────────────────
    cum_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Retorno Cumulativo — {ticker}",
        "description": (
            "Retorno percentual acumulado desde o primeiro dia do período. "
            "Eixo único em %."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": f"{ticker} — Retorno Cumulativo (%)",
                        "data": cum_returns_pct,
                        "borderColor": "#0d9488",
                        "backgroundColor": "rgba(13,148,136,0.1)",
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
                        "position": "left",
                        "title": {"display": True, "text": "Retorno cumulativo (%)"},
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        # price_full_datasets mirrors chart_data.data.datasets order (single dataset now).
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": cum_returns_pct, "label": "Retorno Cum. (%)"},
        ],
        "price_full_data": cum_returns_pct,
    }

    # ── Drawdown chart (always ≤ 0; red fill, single left axis %) ──────────
    dd_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Drawdown — {ticker}",
        "description": (
            "Queda do pico de preço mais recente (peak-to-trough). "
            "0% = no novo máximo; -30% = 30% abaixo do pico. Eixo único em %."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Drawdown (%)",
                        "data": drawdowns_pct,
                        "borderColor": "#ef4444",
                        "backgroundColor": "rgba(239,68,68,0.15)",
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": "origin",
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
                        "position": "left",
                        "title": {"display": True, "text": "Drawdown (%)"},
                        # Drawdowns are always ≤ 0.
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        # price_full_datasets mirrors chart_data.data.datasets order (single dataset now).
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": drawdowns_pct, "label": "Drawdown (%)"},
        ],
        "price_full_data": drawdowns_pct,
    }

    # ── KPI table: total return + max drawdown + period days ───────────────
    # KPI uses the RAW fractions (fmt_pct formats 0.15 -> "15,00%").
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
