"""skills/b3/price/report/spread.py -- Bid-Ask Spread tab builder (v1.6).

Sections:
  1. Spread absoluto (R$) chart  -- best_ask - best_bid over time
  2. Spread percentual (%) chart -- spread / midpoint * 100
  3. Bid/Ask/Close chart         -- 3 lines: best_bid (green), best_ask (red), close (teal)
  4. Liquidez KPI table          -- mean/median spread, % days with quotes, etc.

Uses ``column_align`` to right-align numeric columns in the KPI table.

[v1.6] New file. Reads best_bid + best_ask from cotahist (already in the
schema as REAL columns; can be NULL on illiquid days -- handled gracefully
by carry-forward of None).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_num, fmt_int, _is_missing


_COLOR_BID = "#0d9488"     # teal (per task spec)
_COLOR_ASK = "#3b82f6"     # blue (per task spec)
_COLOR_CLOSE = "#9ca3af"   # gray (per task spec)
_COLOR_SPREAD = "#f59e0b"  # orange (per task spec)


def build_spread_sections(
    ticker: str,
    dates: list[str],
    best_bids: list[float | None],
    best_asks: list[float | None],
    closes: list[float | None],
    volumes: list[float | None] | None = None,
    trade_counts: list[int | None] | None = None,
) -> list[dict]:
    """Build the Bid-Ask Spread tab: spread charts + bid/ask/close + KPI table.

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings
        best_bids:    daily best bid (R$) -- can be None on illiquid days
        best_asks:    daily best ask (R$) -- can be None on illiquid days
        closes:       daily close prices (R$) -- for the bid/ask/close chart
        volumes:      daily financial volume (R$) -- for the liquidity KPI
        trade_counts: daily trade count -- for the liquidity KPI

    Returns:
        Four sections: spread absoluto chart + spread percentual chart +
        bid/ask/close chart + liquidez KPI table. If no bid/ask data is
        available, returns a single text section noting the absence.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Bid-Ask Spread — {ticker}",
            "text": "Sem dados de cotacao disponiveis.",
        }]

    # Compute spread + spread_pct inline (engines.compute_bid_ask_spread and
    # compute_spread_pct are also available, but we compute here to keep this
    # builder self-contained + avoid a circular import with engines).
    n = len(dates)
    spreads_abs: list[float | None] = [None] * n
    spreads_pct: list[float | None] = [None] * n
    for i in range(n):
        b = best_bids[i] if i < len(best_bids) else None
        a = best_asks[i] if i < len(best_asks) else None
        c = closes[i] if i < len(closes) else None
        if b is None or a is None:
            continue
        spreads_abs[i] = a - b
        # [v1.6] spread_pct = (ask - bid) / close * 100 (per task spec for
        # compute_spread_pct in engines.py). Close is the reference price;
        # when close is None or <= 0, spread_pct is None.
        if c is not None and c > 0:
            spreads_pct[i] = (a - b) / c * 100.0

    # If NO valid spread observations, return a text section.
    valid_spreads = [s for s in spreads_abs if not _is_missing(s)]
    if not valid_spreads:
        return [{
            "type": "text",
            "title": f"Bid-Ask Spread — {ticker}",
            "text": (
                "Sem dados de bid/ask para o periodo. As colunas best_bid e "
                "best_ask do COTAHIST estao ausentes ou NULL para todos os "
                "pregoes selecionados (comum em tickers de baixa liquidez)."
            ),
        }]

    # ── 1. Spread absoluto (R$) chart ─────────────────────────────────────
    spread_abs_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"Spread Absoluto — {ticker}",
        "description": (
            "Spread absoluto (R$) = best_ask - best_bid por pregao. Valores "
            "altos indicam baixa liquidez ou alta volatilidade intradia; "
            "valores baixos indicam mercado liquido + tight."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [{
                    "type": "line",
                    "label": "Spread (R$)",
                    "data": spreads_abs,
                    "borderColor": _COLOR_SPREAD,
                    "backgroundColor": "rgba(245,158,11,0.08)",
                    "borderWidth": 1.5,
                    "pointRadius": 0,
                    "pointHoverRadius": 3,
                    "tension": 0.2,
                    "fill": True,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": "Spread (R$)"}},
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [{"data": spreads_abs, "label": "Spread (R$)"}],
        "price_full_data": spreads_abs,
    }

    # ── 2. Spread percentual (%) chart ────────────────────────────────────
    spread_pct_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"Spread Percentual — {ticker}",
        "description": (
            "Spread percentual = spread / fechamento * 100. Normaliza a "
            "comparacao entre tickers de precos diferentes (1 centavo de "
            "spread em R$10 = 10 bps; em R$100 = 1 bp). 1 bp = 0,01%."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [{
                    "type": "line",
                    "label": "Spread (%)",
                    "data": spreads_pct,
                    "borderColor": _COLOR_ASK,
                    "backgroundColor": "rgba(239,68,68,0.08)",
                    "borderWidth": 1.5,
                    "pointRadius": 0,
                    "pointHoverRadius": 3,
                    "tension": 0.2,
                    "fill": True,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": "Spread (%)"}},
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [{"data": spreads_pct, "label": "Spread (%)"}],
        "price_full_data": spreads_pct,
    }

    # ── 3. Bid / Ask / Close chart ────────────────────────────────────────
    bid_ask_close_chart: dict[str, Any] = {
        "type": "chart",
        "title": f"Bid / Ask / Close — {ticker}",
        "description": (
            "Melhor bid (verde), melhor ask (vermelho) e fechamento (teal) "
            "por pregao. A area entre bid e ask e o spread intradia; quando "
            "bid e ask se cruzam ou se afastam, indica mudancas de liquidez."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Best Bid",
                        "data": best_bids,
                        "borderColor": _COLOR_BID,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "Best Ask",
                        "data": best_asks,
                        "borderColor": _COLOR_ASK,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": False,
                    },
                    {
                        "type": "line",
                        "label": "Close",
                        "data": closes,
                        "borderColor": _COLOR_CLOSE,
                        "borderWidth": 1.5,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.1,
                        "fill": False,
                        "borderDash": [2, 2],
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"ticks": {"maxTicksLimit": 12}},
                    "y": {"title": {"display": True, "text": "Preco (R$)"}},
                },
                "plugins": {"legend": {"display": True, "position": "top"}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": dates,
        "price_full_datasets": [
            {"data": best_bids, "label": "Best Bid"},
            {"data": best_asks, "label": "Best Ask"},
            {"data": closes, "label": "Close"},
        ],
        "price_full_data": closes,
    }

    # ── 4. Liquidez KPI table ─────────────────────────────────────────────
    valid_pct = [p for p in spreads_pct if not _is_missing(p)]
    valid_abs = [s for s in spreads_abs if not _is_missing(s)]

    # Mean / median over the most-recent 252 business days (~1 year).
    recent_abs = valid_abs[-252:] if valid_abs else []
    recent_pct = valid_pct[-252:] if valid_pct else []

    mean_abs = (sum(recent_abs) / len(recent_abs)) if recent_abs else None
    mean_pct = (sum(recent_pct) / len(recent_pct)) if recent_pct else None
    median_abs = sorted(recent_abs)[len(recent_abs) // 2] if recent_abs else None
    median_pct = sorted(recent_pct)[len(recent_pct) // 2] if recent_pct else None
    max_abs = max(recent_abs) if recent_abs else None
    min_abs = min(recent_abs) if recent_abs else None

    # % of days with valid bid/ask quotes (vs total days in the window).
    days_with_quotes = len(valid_abs)
    pct_days_with_quotes = (
        (days_with_quotes / n * 100.0) if n > 0 else None
    )

    # Average volume + trade count over the most-recent 252 days (if provided).
    avg_vol_252 = None
    if volumes:
        valid_vols = [v for v in volumes[-252:] if not _is_missing(v) and v > 0]
        if valid_vols:
            avg_vol_252 = sum(valid_vols) / len(valid_vols)
    avg_trades_252 = None
    if trade_counts:
        valid_tc = [t for t in trade_counts[-252:] if t is not None and t > 0]
        if valid_tc:
            avg_trades_252 = sum(valid_tc) / len(valid_tc)

    kpi_rows = [
        ["Spread medio (R$)",         fmt_num(mean_abs, 4)],
        ["Spread mediano (R$)",       fmt_num(median_abs, 4)],
        ["Spread medio (%)",          fmt_num(mean_pct, 4)],
        ["Spread mediano (%)",        fmt_num(median_pct, 4)],
        ["Spread maximo (R$)",        fmt_num(max_abs, 4)],
        ["Spread minimo (R$)",        fmt_num(min_abs, 4)],
        ["Pregoes com cotacao bid/ask",
         f"{fmt_int(days_with_quotes)} ({fmt_num(pct_days_with_quotes, 1)}%)"],
        ["Volume medio 252D (R$)",    fmt_num(avg_vol_252, 0) if avg_vol_252 is not None else "—"],
        ["Negocios medios 252D",      fmt_int(avg_trades_252) if avg_trades_252 is not None else "—"],
    ]

    kpi_section: dict[str, Any] = {
        "type": "table",
        "title": "Estatisticas de Liquidez",
        "description": (
            "Estatisticas de spread bid/ask + liquidez nos ultimos 252 "
            "pregoes (~1 ano). Spread baixo + alto numero de negocios = "
            "mercado liquido; spread alto + baixo numero de negocios = "
            "mercado iliquido (custo de transacao elevado)."
        ),
        "columns": ["Metrica", "Valor"],
        "rows": kpi_rows,
        # Right-align the numeric "Valor" column (index 1); left-align the
        # "Metrica" label (0).
        "column_align": ["left", "right"],
    }

    return [spread_abs_chart, spread_pct_chart, bid_ask_close_chart, kpi_section]
