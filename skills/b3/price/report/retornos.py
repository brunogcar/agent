"""skills/b3/price/report/retornos.py -- Retornos tab builder.

Cumulative return chart + drawdown chart + total return KPI + max drawdown KPI.

[v1.1] The dual-axis price overlay (right axis) was removed from both the
cumulative-return + drawdown charts — they now show ONLY the return/drawdown
series on a single left axis. The Cotacao tab's Volume Diário chart keeps
its dual-axis price overlay (volume + price is the intended pattern there).
Chart data values are multiplied by 100 so the y-axis (titled "%") matches
the displayed values (was: fractions like 0.15 shown with a "(%)" title).

[v1.3] Added a dividend-adjusted cumulative return chart + KPI row. The
adjusted return uses the backward-adjusted close series (historical
prices minus dividends paid after that date), giving the true total
return including reinvested dividends. The raw return chart stays as-is
for comparison. If no dividends were paid in the period, the adjusted
return equals the raw return (no extra chart is emitted).
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
    adj_cum_returns: list[float | None] | None = None,
) -> list[dict]:
    """Build the Retornos tab: cumulative return + drawdown + KPIs.

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings
        closes:       daily close prices (UNUSED since v1.1 — was the dual-axis
                      price overlay; kept in signature for caller compat)
        cum_returns:  cumulative return from first close (fraction, e.g. 0.15 = +15%)
        drawdowns:    drawdown from running peak (negative fraction, 0 = at peak)
        adj_cum_returns: [v1.3] cumulative return from the dividend-adjusted
                      close series. When None or all-None, the adjusted chart
                      + KPI row are omitted.

    Returns:
        Three or four sections: cumulative-return chart + (optional adjusted
        cumulative-return chart) + drawdown chart + KPI table.

    [v1.1] Charts display values × 100 so the y-axis "%" title matches the
    plotted data (was: raw fractions 0.15 shown with "(%)" title). The
    dual-axis price overlay was removed.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Retornos",
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

    sections: list[dict] = []

    # ── Cumulative return chart (single left axis, %) ─────────────────────
    cum_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Retorno Cumulativo",
        "description": (
            "Retorno percentual acumulado desde o primeiro dia do período (preço apenas). "
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
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": cum_returns_pct, "label": "Retorno Cum. (%)"},
        ],
        "price_full_data": cum_returns_pct,
    }
    sections.append(cum_section)

    # [v1.3] Dividend-adjusted cumulative return chart.
    adj_total_return = None
    if adj_cum_returns:
        adj_cum_pct = [
            (v * 100) if not _is_missing(v) else None
            for v in adj_cum_returns
        ]
        has_adj = any(v is not None for v in adj_cum_pct)
        if has_adj:
            valid_adj = [v for v in adj_cum_returns if not _is_missing(v)]
            adj_total_return = valid_adj[-1] if valid_adj else None
            adj_section: dict[str, Any] = {
                "type": "chart",
                "title": f"Retorno Cumulativo Ajustado",
                "description": (
                    "Retorno percentual acumulado ajustado por dividendos "
                    "(backward adjustment). Preços históricos são reduzidos "
                    "pelo valor dos dividendos pagos após cada data, tornando "
                    "a série comparável ao fechamento atual. A diferença vs o "
                    "retorno bruto = impacto dos dividendos reinvestidos."
                ),
                "chart_data": {
                    "type": "line",
                    "data": {
                        "labels": dates,
                        "datasets": [
                            {
                                "type": "line",
                                "label": f"{ticker} — Retorno Ajustado (%)",
                                "data": adj_cum_pct,
                                "borderColor": "#7c3aed",
                                "backgroundColor": "rgba(124,58,237,0.1)",
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
                                "title": {"display": True, "text": "Retorno cumulativo ajustado (%)"},
                            },
                        },
                        "plugins": {"legend": {"display": True, "position": "top"}},
                    },
                },
                "price_range_selector": True,
                "price_full_labels": dates,
                "price_full_datasets": [
                    {"data": adj_cum_pct, "label": "Retorno Ajustado (%)"},
                ],
                "price_full_data": adj_cum_pct,
            }
            sections.append(adj_section)

            # [v1.5] Dividend return chart = adjusted - raw (dividend contribution).
            div_return_pct: list[float | None] = []
            for a, r in zip(adj_cum_pct, cum_returns_pct):
                if a is not None and r is not None:
                    div_return_pct.append(a - r)
                else:
                    div_return_pct.append(None)
            div_total_return = None
            valid_div = [v for v in div_return_pct if v is not None]
            if valid_div:
                div_total_return = valid_div[-1] / 100.0  # back to fraction for fmt_pct
            div_section: dict[str, Any] = {
                "type": "chart",
                "title": f"Retorno de Dividendos",
                "description": (
                    "Diferença entre o retorno ajustado e o retorno bruto = "
                    "contribuição dos dividendos. Mostra quanto do retorno total "
                    "veio de dividendos reinvestidos vs valorização do preço. "
                    "Linha crescente = dividendos acumulando ao longo do tempo."
                ),
                "chart_data": {
                    "type": "line",
                    "data": {
                        "labels": dates,
                        "datasets": [
                            {
                                "type": "line",
                                "label": f"{ticker} — Retorno de Dividendos (%)",
                                "data": div_return_pct,
                                "borderColor": "#22c55e",
                                "backgroundColor": "rgba(34,197,94,0.15)",
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
                                "title": {"display": True, "text": "Retorno de dividendos (%)"},
                            },
                        },
                        "plugins": {"legend": {"display": True, "position": "top"}},
                    },
                },
                "price_range_selector": True,
                "price_full_labels": dates,
                "price_full_datasets": [
                    {"data": div_return_pct, "label": "Retorno Div. (%)"},
                ],
                "price_full_data": div_return_pct,
            }
            sections.append(div_section)

    # ── Drawdown chart (always ≤ 0; red fill, single left axis %) ──────────
    dd_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Drawdown",
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
                    },
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": drawdowns_pct, "label": "Drawdown (%)"},
        ],
        "price_full_data": drawdowns_pct,
    }
    sections.append(dd_section)

    # ── KPI table: total return + adjusted return + max drawdown + days ────
    # KPI uses the RAW fractions (fmt_pct formats 0.15 -> "15,00%").
    valid_cum = [c for c in cum_returns if not _is_missing(c)]
    total_return = valid_cum[-1] if valid_cum else None
    valid_dd = [d for d in drawdowns if not _is_missing(d)]
    max_dd = min(valid_dd) if valid_dd else None

    kpi_rows = [
        ["Retorno Cumulativo Total",         fmt_pct(total_return or 0)],
    ]
    if adj_total_return is not None:
        kpi_rows.append(["Retorno Cumulativo Ajustado", fmt_pct(adj_total_return)])
    if div_total_return is not None:
        kpi_rows.append(["Retorno de Dividendos",        fmt_pct(div_total_return)])
    kpi_rows.extend([
        ["Drawdown Máximo",                  fmt_pct(max_dd or 0)],
        ["Dias no Período",                  str(len(dates))],
    ])

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": f"Resumo de Performance ({len(dates)} dias)",
        "columns": ["Métrica", "Valor"],
        "rows": kpi_rows,
    }
    if adj_total_return is not None:
        kpi_section["note"] = (
            "Retorno Cumulativo Total = preço apenas. "
            "Retorno Cumulativo Ajustado = preço + dividendos reinvestidos "
            "(backward adjustment). A diferença entre os dois = impacto dos "
            "dividendos no período."
        )
    # [v7] Resumo de Performance moved to TOP. Charts collapsible.
    sections = [kpi_section]

    # [v7] Make charts collapsible (collapsed by default)
    cum_section["collapsible"] = True
    cum_section["collapsible_open"] = False
    sections.append(cum_section)

    if adj_total_return is not None:
        adj_section["collapsible"] = True
        adj_section["collapsible_open"] = False
        sections.append(adj_section)

    dd_section["collapsible"] = True
    dd_section["collapsible_open"] = False
    sections.append(dd_section)

    return sections
