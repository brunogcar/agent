"""skills/b3/price/report/medias.py -- Médias Móveis tab builder.

Line chart with price + 4 moving averages (MA20/50/100/200) + crossovers table.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_brl, fmt_num


# MA line colors — kept in sync with cotacao.py.
_MA_COLORS = {
    "MA20":  "#facc15",
    "MA50":  "#fb923c",
    "MA100": "#ec4899",
    "MA200": "#ef4444",
}


def build_medias_sections(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
    ma20: list[float | None],
    ma50: list[float | None],
    ma100: list[float | None],
    ma200: list[float | None],
    crossovers: list[dict] | None = None,
) -> list[dict]:
    """Build the Médias Móveis tab: SMA chart + crossovers table.

    Args:
        ticker:      PETR4
        dates:       list of YYYY-MM-DD strings (aligned with closes/MAs)
        closes:      daily close prices (None for missing)
        ma20/50/100/200: SMA series (None for warmup period)
        crossovers:  list of crossover dicts from find_ma_crossovers()
                     [{"date", "type": "golden"|"death", "signal", ...}]

    Returns:
        Two sections: line chart (price + 4 MAs) + crossovers table.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Médias Móveis — {ticker}",
            "text": "Sem dados de preço para calcular médias móveis.",
        }]

    ma_datasets = []
    for label, ma in [("MA20", ma20), ("MA50", ma50),
                       ("MA100", ma100), ("MA200", ma200)]:
        ma_datasets.append({
            "type": "line",
            "label": label,
            "data": ma,
            "borderColor": _MA_COLORS[label],
            "borderWidth": 1.5,
            "pointRadius": 0,
            "pointHoverRadius": 3,
            "tension": 0,
            "fill": False,
        })

    chart_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Médias Móveis — {ticker}",
        "description": (
            "Preço de fechamento + médias móveis simples 20/50/100/200 dias. "
            "Cruzamentos indicam sinais de compra (Ouro) ou venda (Morte)."
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
                        "borderColor": "#0d9488",
                        "borderWidth": 1.2,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": False,
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
                        "title": {"display": True, "text": "Preço (R$)"},
                    },
                },
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        # [v2] MUST mirror chart_data.data.datasets order (price, MA20, MA50,
        # MA100, MA200) so filterPriceChart keeps every series aligned when a
        # range button is clicked. Previously only the 4 MAs were listed, so
        # the price line updated but the MAs stayed at full range → misaligned.
        "price_full_datasets": [
            {"data": closes, "label": f"{ticker} — Fechamento"},
            {"data": ma20, "label": "MA20"},
            {"data": ma50, "label": "MA50"},
            {"data": ma100, "label": "MA100"},
            {"data": ma200, "label": "MA200"},
        ],
        "price_full_data": closes,
    }

    # Crossovers table.
    rows = []
    if crossovers:
        # Most recent first — users want to see the latest signals at the top.
        for x in sorted(crossovers, key=lambda c: c.get("date", ""), reverse=True):
            t = x.get("type", "")
            icon = "🟢" if t == "golden" else "🔴" if t == "death" else "•"
            rows.append([
                x.get("date", "—"),
                f"{icon} {t.title()}",
                x.get("signal", "—"),
                x.get("fast_label", "—"),
                fmt_num(x.get("fast")),
                x.get("slow_label", "—"),
                fmt_num(x.get("slow")),
            ])

    table_section: dict[str, Any] = {
        "type": "table",
        "title": "Cruzamentos de Médias",
        "description": (
            "Pontos onde a média rápida cruzou a média lenta. "
            "Ouro (compra) = rápida subiu acima da lenta. "
            "Morte (venda) = rápida caiu abaixo da lenta."
        ),
        "columns": ["Data", "Tipo", "Sinal", "Rápida", "Valor", "Lenta", "Valor"],
        "rows": rows or [["—", "—", "Sem cruzamentos no período", "—", "—", "—", "—"]],
    }

    return [chart_section, table_section]
