"""skills/b3/price/report/volume.py -- Volume tab builder.

Volume bars (colored by up/down day) + 20-day volume MA line + average volume KPI.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_compact, fmt_int, _is_missing


_COLOR_UP = "#22c55e"
_COLOR_DOWN = "#ef4444"


def build_volume_sections(
    ticker: str,
    dates: list[str],
    volumes: list[float | None],
    closes: list[float | None],
    opens: list[float | None],
    vol_ma20: list[float | None] | None = None,
) -> list[dict]:
    """Build the Volume tab: volume bars + 20D MA line + average KPI.

    Args:
        ticker:   PETR4
        dates:    list of YYYY-MM-DD strings
        volumes:  daily financial volume (R$) aligned with dates
        closes:   daily close prices (for up/down color classification)
        opens:    daily open prices (for up/down color classification)
        vol_ma20: 20-day SMA of volume (None for warmup). If None, computed here
                  from volumes (using the engines' compute_sma).

    Returns:
        Two sections: volume bars chart (with MA20 line overlay) + volume stats KPI.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Volume — {ticker}",
            "text": "Sem dados de volume disponíveis.",
        }]

    # Color per day: green if close >= open (up day), red otherwise.
    # Falls back to green when open/close missing.
    colors: list[str] = []
    for i in range(len(dates)):
        c = closes[i] if i < len(closes) else None
        o = opens[i] if i < len(opens) else None
        if c is not None and o is not None:
            colors.append(_COLOR_UP if c >= o else _COLOR_DOWN)
        else:
            colors.append(_COLOR_UP)

    # [v2] The MM20 volume overlay was removed per user request. A close-PRICE
    # line on the right-hand axis (dual axis) is added instead so volume can be
    # read alongside price action — same pattern as the Volume Diário chart in
    # the Cotação tab.
    _PRICE_COLOR = "#0d9488"  # teal

    datasets: list[dict] = [
        {
            "type": "bar",
            "label": "Volume (R$)",
            "data": volumes,
            "backgroundColor": colors,
            "borderColor": colors,
            "borderWidth": 0,
            "order": 2,
        },
        {
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
            "order": 1,
        },
    ]

    chart_section: dict[str, Any] = {
        "type": "chart",
        "title": f"Volume — {ticker}",
        "description": (
            "Volume financeiro diário (R$, eixo esquerdo). Verde: fechamento ≥ "
            "abertura (alta). Vermelho: fechamento < abertura (baixa). Linha teal: "
            "preço de fechamento (eixo direito)."
        ),
        "chart_data": {
            "type": "bar",
            "data": {"labels": dates, "datasets": datasets},
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
                "plugins": {"legend": {"display": True, "position": "top"}},
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

    # Average volume KPI (last 20D, last 60D, last 252D).
    valid_vols = [v for v in volumes if not _is_missing(v) and v > 0]
    avg_20d = (sum(valid_vols[-20:]) / len(valid_vols[-20:])) if len(valid_vols) >= 1 else None
    avg_60d = (sum(valid_vols[-60:]) / len(valid_vols[-60:])) if len(valid_vols) >= 1 else None
    avg_252d = (sum(valid_vols[-252:]) / len(valid_vols[-252:])) if len(valid_vols) >= 1 else None

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": "Estatísticas de Volume",
        "columns": ["Janela", "Volume Médio (R$)"],
        "rows": [
            ["20 dias úteis (1M)", fmt_compact(avg_20d)],
            ["60 dias úteis (3M)", fmt_compact(avg_60d)],
            ["252 dias úteis (1A)", fmt_compact(avg_252d)],
            ["Dias com volume registrado", fmt_int(len(valid_vols))],
        ],
    }

    return [chart_section, kpi_section]
