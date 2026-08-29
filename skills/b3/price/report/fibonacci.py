"""skills/b3/price/report/fibonacci.py -- Fibonacci tab builder (v1.3).

Builds 10 sections organized BY SWING (not by category). For each swing
timeframe (Swing_4, Swing_12, Swing_52), emits 3 collapsible tables:
  - Níveis de Fibonacci — Swing_X (collapsed by default)
  - Trade Setup — COMPRA — Swing_X (expanded by default)
  - Trade Setup — VENDA — Swing_X (expanded by default)

Then a single non-collapsible dividend-adjustments table at the end.

The layout makes it easy to visualize one swing at a time: the Níveis
table is collapsed (reference, not always needed), the COMPRA + VENDA
trade-setup tables are expanded (the actionable info).

The 3 swing timeframes mirror the user's spreadsheet:
  - Swing_4  = 30 calendar days  (4 weeks  / 1 month)
  - Swing_12 = 90 calendar days  (12 weeks / 3 months)
  - Swing_52 = 365 calendar days (52 weeks / 1 year)

Trade-setup formulas (verified against the user's spreadsheet):
  COMPRA: Entrada 1 = High - range×0.382, Entrada 2 = High - range×0.618
          Alvo 1 = High + range×0.382, Alvo 2 = High + range×0.618
          STOP = Entrada 2 - range×0.10
  VENDA:  Entrada 1 = Low + range×0.382, Entrada 2 = Low + range×0.618
          Alvo 1 = Low - range×0.382, Alvo 2 = Low - range×0.618
          STOP = Entrada 2 + range×0.10
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import fmt_brl, fmt_pct, _is_missing


# Swing timeframes (calendar days for the lookback window).
SWING_LOOKBACKS = [
    {"label": "Swing_4",  "days": 30,  "desc": "4 semanas / 1 mês"},
    {"label": "Swing_12", "days": 90,  "desc": "12 semanas / 3 meses"},
    {"label": "Swing_52", "days": 365, "desc": "52 semanas / 1 ano"},
]


def _fmt_price(v: float | None) -> str:
    """Format a price as BRL (compact, no R$ prefix for chart labels)."""
    if v is None or _is_missing(v):
        return "—"
    return fmt_brl(v, suffix=False)


def build_fibonacci_sections(
    ticker: str,
    dates: list[str],
    closes: list[float | None],
    highs: list[float | None],
    lows: list[float | None],
    current_price: float | None,
    swings: list[dict],
    adjustments: list[dict],
) -> list[dict]:
    """Build the Fibonacci tab: 10 sections organized BY SWING.

    [v1.3-v4] Layout: for each swing (Swing_4 → Swing_12 → Swing_52),
    emit 3 collapsible tables:
      1. Níveis de Fibonacci — Swing_X (collapsed by default)
      2. Trade Setup — COMPRA — Swing_X (expanded by default)
      3. Trade Setup — VENDA — Swing_X (expanded by default)
    Then a single non-collapsible dividend-adjustments table at the end.

    The description (e.g. "4 semanas / 1 mês") appears once in each
    table's description field, NOT in the title (cleaner titles).

    Args:
        ticker:       PETR4
        dates:        list of YYYY-MM-DD strings (unused now — was for the chart)
        closes:       daily close prices (unused now — was for the chart)
        highs:        daily highs (used by find_swing_extremes — passed for completeness)
        lows:         daily lows (used by find_swing_extremes — passed for completeness)
        current_price: latest close price (for % distance calculations)
        swings:       list of swing dicts from find_swing_extremes (one per timeframe)
        adjustments:  list of dividend adjustment dicts from compute_adjusted_close

    Returns:
        10 sections: 9 collapsible tables (3 per swing, grouped by swing)
        + 1 non-collapsible dividend-adjustments table.
    """
    if not dates:
        return [{
            "type": "text",
            "title": f"Fibonacci",
            "text": "Sem dados de preço para calcular níveis de Fibonacci.",
        }]

    from skills.b3.price.engines import (
        compute_fibonacci_levels, compute_fibonacci_trade_setup, FIB_LEVELS)

    sections: list[dict] = []

    def _pct(target: float) -> dict:
        """Format % vs current price as a cell dict with green/red color."""
        if current_price is None or current_price == 0:
            return {"text": "—"}
        pct = (target - current_price) / current_price
        s = fmt_pct(pct)
        return {"text": s, "color": "#22c55e" if pct >= 0 else "#ef4444"}

    def _fmt_date(iso: str) -> str:
        """Convert YYYY-MM-DD to DD/MM/YYYY."""
        if not iso or iso == "—":
            return "—"
        parts = iso.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return iso

    # ── Per-swing sections (grouped by swing, not by category) ─────────────
    for i, sw in enumerate(swings):
        if sw.get("high_price") is None:
            continue
        lbl = SWING_LOOKBACKS[i]["label"]
        desc = SWING_LOOKBACKS[i]["desc"]
        levels = compute_fibonacci_levels(sw["high_price"], sw["low_price"])
        setup = compute_fibonacci_trade_setup(sw["high_price"], sw["low_price"])
        c = setup["compra"]
        v = setup["venda"]

        # 1. Níveis de Fibonacci — Swing_X (collapsed by default)
        niveis_rows: list[list[str]] = []
        for L in FIB_LEVELS:
            price = levels.get(L)
            tag = ""
            if L == 0.382:
                tag = "← Entrada 1 / Alvo 1"
            elif L == 0.618:
                tag = "← Entrada 2 / Alvo 2"
            elif L == 1.000:
                tag = "← Mínima (retracement completo)"
            niveis_rows.append([f"{L:.3f}", _fmt_price(price), tag])

        sections.append({
            "type": "table",
            "title": f"Níveis de Fibonacci — {lbl}",
            "description": (
                f"{desc}. "
                f"Máxima: {_fmt_price(sw['high_price'])} ({_fmt_date(sw['high_date'])}) • "
                f"Mínima: {_fmt_price(sw['low_price'])} ({_fmt_date(sw['low_date'])}) • "
                f"Intervalo: {_fmt_price(sw['range'])}. "
                "Nível 0 = Máxima, nível 1 = Mínima, níveis >1 = extensões."
            ),
            "columns": ["Nível", "Preço (R$)", "Nota"],
            "rows": niveis_rows,
            "column_align": ["left", "right", "left"],
            "collapsible": True,
            "collapsible_open": False,  # collapsed by default
        })

        # 2. Trade Setup — COMPRA — Swing_X (expanded by default)
        sections.append({
            "type": "table",
            "title": f"Trade Setup — COMPRA — {lbl}",
            "description": (
                f"{desc}. "
                "COMPRA (comprar na retração do topo). Entrada 1 = 0,382, "
                "Entrada 2 = 0,618, Alvo 1 = extensão 0,382, Alvo 2 = extensão "
                "0,618, STOP = 10% do intervalo além da Entrada 2."
            ),
            "columns": ["Nível", "Preço (R$)", "% vs Atual"],
            "rows": [
                ["Entrada 1", _fmt_price(c["entrada_1"]), _pct(c["entrada_1"])],
                ["Entrada 2", _fmt_price(c["entrada_2"]), _pct(c["entrada_2"])],
                ["Alvo 1",    _fmt_price(c["alvo_1"]),    _pct(c["alvo_1"])],
                ["Alvo 2",    _fmt_price(c["alvo_2"]),    _pct(c["alvo_2"])],
                ["STOP",      _fmt_price(c["stop"]),      _pct(c["stop"])],
            ],
            "column_align": ["left", "right", "right"],
            "note": (
                "Preço atual: " + _fmt_price(current_price) + ". "
                "Sinais são pontos de referência — NÃO são recomendações."
            ),
            "collapsible": True,
            "collapsible_open": True,  # expanded by default
        })

        # 3. Trade Setup — VENDA — Swing_X (expanded by default)
        sections.append({
            "type": "table",
            "title": f"Trade Setup — VENDA — {lbl}",
            "description": (
                f"{desc}. "
                "VENDA (vender na alta do fundo). Entrada 1 = 0,382, "
                "Entrada 2 = 0,618, Alvo 1 = extensão 0,382, Alvo 2 = extensão "
                "0,618, STOP = 10% do intervalo além da Entrada 2."
            ),
            "columns": ["Nível", "Preço (R$)", "% vs Atual"],
            "rows": [
                ["Entrada 1", _fmt_price(v["entrada_1"]), _pct(v["entrada_1"])],
                ["Entrada 2", _fmt_price(v["entrada_2"]), _pct(v["entrada_2"])],
                ["Alvo 1",    _fmt_price(v["alvo_1"]),    _pct(v["alvo_1"])],
                ["Alvo 2",    _fmt_price(v["alvo_2"]),    _pct(v["alvo_2"])],
                ["STOP",      _fmt_price(v["stop"]),      _pct(v["stop"])],
            ],
            "column_align": ["left", "right", "right"],
            "note": (
                "Preço atual: " + _fmt_price(current_price) + ". "
                "Sinais são pontos de referência — NÃO são recomendações."
            ),
            "collapsible": True,
            "collapsible_open": True,  # expanded by default
        })

    # ── Dividend adjustments table (NOT collapsible) ──────────────────────
    div_rows: list[list[str]] = []
    for adj in adjustments:
        div_rows.append([
            _fmt_date(adj.get("ex_date", "—")),
            _fmt_price(adj.get("rate")),
            _fmt_date(adj.get("payment_date", "—")),
            adj.get("isin_code", "—"),
        ])

    sections.append({
        "type": "table",
        "title": "Ajuste de Proventos",
        "description": (
            "Dividendos em dinheiro pagos durante o período analisado, "
            "filtrados pelo ISIN do ticker (garante que apenas dividendos "
            "da classe de ação correta sejam aplicados — ex.: PETR4 não "
            "recebe dividendos de PETR3). O ajuste backward subtrai o "
            "dividendo de todos os preços anteriores à data ex-dividendo, "
            "tornando a série histórica comparável ao fechamento atual. "
            "Usado no cálculo do Retorno Ajustado na aba Retornos."
        ),
        "columns": ["Data Ex-Div", "Valor (R$)", "Data Pagamento", "ISIN"],
        "rows": div_rows if div_rows else [["—", "—", "Nenhum dividendo no período", "—"]],
        "column_align": ["left", "right", "left", "left"],
    })

    return sections
