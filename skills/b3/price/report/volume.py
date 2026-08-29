"""skills/b3/price/report/volume.py -- Volume tab builder.

Volume bars (colored by up/down day) + price overlay + trade count chart +
contracts chart + average volume KPI.

[v1.5] Added trade_count + contracts charts — both use the dual-axis
pattern (bars left, price right) matching the existing volume chart.
Trade count shows number of individual trades (negócios) per day;
contracts shows total shares/contracts traded (quantity, not R$).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_compact, fmt_int, _is_missing


_COLOR_UP = "#22c55e"
_COLOR_DOWN = "#ef4444"
_PRICE_COLOR = "#0d9488"  # teal


def _up_down_colors(closes: list[float | None], opens: list[float | None]) -> list[str]:
    """Build a per-day color list: green if close >= open, red otherwise."""
    colors: list[str] = []
    for i in range(len(closes)):
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        if c is not None and o is not None:
            colors.append(_COLOR_UP if c >= o else _COLOR_DOWN)
        else:
            colors.append(_COLOR_UP)
    return colors


def build_volume_sections(
    ticker: str,
    dates: list[str],
    volumes: list[float | None],
    closes: list[float | None],
    opens: list[float | None],
    vol_ma20: list[float | None] | None = None,
    trade_counts: list[int | None] | None = None,
    contracts: list[int | None] | None = None,
) -> list[dict]:
    """Build the Volume tab: volume bars + trade count + contracts + KPI.

    [v1.5] Added trade_count + contracts charts.

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings
        volumes:      daily financial volume (R$) aligned with dates
        closes:       daily close prices (for up/down color + dual-axis overlay)
        opens:        daily open prices (for up/down color classification)
        vol_ma20:     20-day SMA of volume (UNUSED — kept for compat)
        trade_counts: [v1.5] daily number of trades (negócios)
        contracts:    [v1.5] daily total shares/contracts traded (quantity)

    Returns:
        Four sections: volume bars chart + trade count chart + contracts
        chart + volume stats KPI table.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Volume",
            "text": "Sem dados de volume disponíveis.",
        }]

    colors = _up_down_colors(closes, opens)

    def _dual_axis_bar_chart(
        title: str, description: str, data: list, y_label: str,
        data_label: str, chart_type: str = "bar",
    ) -> dict:
        """Build a dual-axis bar chart (data left, price right)."""
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
            "yAxisID": "y1",
            "order": 1,
        }
        bar_ds = {
            "type": "bar",
            "label": data_label,
            "data": data,
            "backgroundColor": colors,
            "borderColor": colors,
            "borderWidth": 0,
            "order": 2,
        }
        return {
            "type": "chart",
            "title": title,
            "description": description,
            "chart_data": {
                "type": "bar",
                "data": {"labels": dates, "datasets": [bar_ds, price_line]},
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "interaction": {"mode": "index", "intersect": False},
                    "scales": {
                        "x": {"ticks": {"maxTicksLimit": 12}},
                        "y": {"position": "left", "title": {"display": True, "text": y_label}},
                        "y1": {
                            "position": "right",
                            "title": {"display": True, "text": "Preço (R$)"},
                            "grid": {"drawOnChartArea": False},
                        },
                    },
                    "plugins": {"legend": {"display": True, "position": "top"}},
                },
            },
            "price_range_selector": True,
            "price_full_labels": dates,
            "price_full_datasets": [
                {"data": data, "label": data_label},
                {"data": closes, "label": f"{ticker} — Preço"},
            ],
            "price_full_data": data,
        }

    # ── 1. Average volume KPI (moved to TOP in v7) ────────────────────────
    valid_vols = [v for v in volumes if not _is_missing(v) and v > 0]
    avg_20d = (sum(valid_vols[-20:]) / len(valid_vols[-20:])) if len(valid_vols) >= 1 else None
    avg_60d = (sum(valid_vols[-60:]) / len(valid_vols[-60:])) if len(valid_vols) >= 1 else None
    avg_252d = (sum(valid_vols[-252:]) / len(valid_vols[-252:])) if len(valid_vols) >= 1 else None

    kpi_rows = [
        ["20 dias úteis (1M)", fmt_compact(avg_20d)],
        ["60 dias úteis (3M)", fmt_compact(avg_60d)],
        ["252 dias úteis (1A)", fmt_compact(avg_252d)],
        ["Dias com volume registrado", fmt_int(len(valid_vols))],
    ]

    if trade_counts:
        valid_tc = [t for t in trade_counts if t is not None and t > 0]
        if valid_tc:
            avg_tc_20d = sum(valid_tc[-20:]) / len(valid_tc[-20:])
            kpi_rows.append(["Média negócios (20D)", fmt_int(avg_tc_20d)])
    if contracts:
        valid_ct = [c for c in contracts if c is not None and c > 0]
        if valid_ct:
            avg_ct_20d = sum(valid_ct[-20:]) / len(valid_ct[-20:])
            kpi_rows.append(["Média ações (20D)", fmt_int(avg_ct_20d)])

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": "Estatísticas de Volume",
        "columns": ["Janela", "Volume Médio (R$)"],
        "rows": kpi_rows,
        "column_align": ["left", "right"],
    }

    sections: list[dict] = [kpi_section]

    # ── 2. Volume financial (R$) chart (collapsible) ──────────────────────
    chart_section = _dual_axis_bar_chart(
        "Volume",
        (
            "Volume financeiro diário (R$, eixo esquerdo). Verde: fechamento ≥ "
            "abertura (alta). Vermelho: fechamento < abertura (baixa). Linha teal: "
            "preço de fechamento (eixo direito)."
        ),
        volumes, "Volume (R$)", "Volume (R$)",
    )
    chart_section["collapsible"] = True
    chart_section["collapsible_open"] = False
    sections.append(chart_section)

    # ── 3. Trade count chart (collapsible) ────────────────────────────────
    if trade_counts:
        tc_section = _dual_axis_bar_chart(
            "Número de Negócios",
            (
                "Quantidade de negócios (trades) por dia (eixo esquerdo). "
                "Diferente do volume financeiro — mostra participação do mercado "
                "(número de investidores transacionando). Linha teal: preço (eixo direito)."
            ),
            trade_counts, "Negócios", "Negócios",
        )
        tc_section["collapsible"] = True
        tc_section["collapsible_open"] = False
        sections.append(tc_section)

    # ── 4. Contracts chart (collapsible) ──────────────────────────────────
    if contracts:
        ct_section = _dual_axis_bar_chart(
            "Quantidade de Ações",
            (
                "Total de ações/contratos negociados por dia (quantidade, eixo "
                "esquerdo). Normaliza a comparação entre tickers de preços "
                "diferentes — 1M ações a R$10 = R$10M vs 1M ações a R$100 = "
                "R$100M (mesma quantidade, volume diferente). Linha teal: preço."
            ),
            contracts, "Ações/Contratos", "Ações/Contratos",
        )
        ct_section["collapsible"] = True
        ct_section["collapsible_open"] = False
        sections.append(ct_section)

    return sections
