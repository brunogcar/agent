"""report/overview.py — Overview tab builders.

Contains the top-level KPI cards + Overview tab sections + radar + heatmap
builders. Each builder returns a section dict shaped for the dashboard
template (see module docstring in ``__init__.py`` for the section schema).

Builders:
  - build_overview_kpis       — 6 KPI cards (top-level dashboard payload)
  - build_overview_sections   — 3 grouped tables (Mercado / Resultado / Balanço)
  - build_valuation_radar     — radar chart, 6 normalized dimensions
  - build_valuation_heatmap   — color-coded valuation metrics table
"""
from __future__ import annotations

from skills.cvm.valuation.report._helpers import _safe_get, _fmt
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── KPI cards (top-level, not inside a section) ──────────────────────────────

def build_overview_kpis(ratios_dict: dict | None) -> list[dict]:
    """Build the 6 KPI cards for the dashboard top-level kpis list."""
    return [
        {"label": "P/L",            "value": _fmt(_safe_get(ratios_dict, "p_l"),            "num")},
        {"label": "P/VPA",          "value": _fmt(_safe_get(ratios_dict, "p_vpa"),          "num")},
        {"label": "EV/EBITDA",      "value": _fmt(_safe_get(ratios_dict, "ev_ebitda"),      "num")},
        {"label": "Dividend Yield", "value": _fmt(_safe_get(ratios_dict, "dividend_yield"), "pct")},
        {"label": "Market Cap",     "value": _fmt(_safe_get(ratios_dict, "market_cap"),     "brl")},
        {"label": "ROE",            "value": _fmt(_safe_get(ratios_dict, "roe"),            "pct")},
    ]


# ── Tab 1: Overview -- summary text + price details collapsible ──────────────

def build_overview_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Overview tab sections: two_column layout matching financials.

    [v2.1] Converted from 3 separate tables to 2 two_column blocks (like
    financials dashboard):
      Block 1: Métricas de Mercado (left) | Resultado TTM (right)
      Block 2: Balanço Patrimonial (left) | Per-share (right)
    """
    sections: list[dict] = []

    # ── Block 1 left: Métricas de Mercado ──
    _MERCADO_ITEMS = [
        ("Market Cap",         "market_cap",         "brl", ""),
        ("EV",                 "ev",                 "brl", "Enterprise Value = Market Cap + Dívida Líquida"),
        ("P/L",                "p_l",                "num", _get_tooltip("lpa")),
        ("P/VPA",              "p_vpa",              "num", _get_tooltip("vpa")),
        ("EV/EBITDA",          "ev_ebitda",          "num", _get_tooltip("ev_ebitda")),
        ("Dividend Yield",     "dividend_yield",     "pct", _get_tooltip("dpa")),
        ("PSR",                "psr",                "num", _get_tooltip("rps")),
        ("DPA (TTM)",          "dpa",                "brl_full", "Dividendos por Ação = Dividendos pagos / total de ações"),
    ]
    mercado_rows = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec, tooltip in _MERCADO_ITEMS
    ]

    # ── Block 1 right: Resultado TTM ──
    _RESULTADO_ITEMS = [
        ("Receita Líquida",    "receita_liquida",    "brl", "Receita total após deduções (DRE 3.01)"),
        ("EBITDA",             "ebitda",             "brl", "EBIT + D&A (Depreciação e Amortização)"),
        ("Lucro Líquido",      "lucro_liquido",      "brl", "Lucro/Prejuízo Consolidado (DRE 3.11)"),
        ("ROE",                "roe",                "pct", _get_tooltip("roe")),
        ("ROA",                "roa",                "pct", _get_tooltip("roa")),
        ("ROIC",               "roic",               "pct", _get_tooltip("roic")),
    ]
    resultado_rows = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec, tooltip in _RESULTADO_ITEMS
    ]

    sections.append({
        "type": "two_column",
        "left_title": "Métricas de Mercado",
        "left_rows": mercado_rows,
        "right_title": "Resultado (TTM)",
        "right_rows": resultado_rows,
        "negative_red": True,
        "positive_green": True,
    })

    # ── Block 2 left: Balanço Patrimonial ──
    _BALANCO_ITEMS = [
        ("Patrimônio Líquido", "patrimonio_liquido", "brl", "Capital próprio dos acionistas (BPP 2.03)"),
        ("Dívida Bruta",       "divida_bruta",       "brl", "Empréstimos Circ + Não Circ (2.01.04 + 2.02.01)"),
        ("Caixa",              "caixa",              "brl", "Caixa e Equivalentes (BPA 1.01.01)"),
        ("Total de Ações",     "total_shares",       "int", "Total de ações outstanding (FRE)"),
    ]
    balanco_rows = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec, tooltip in _BALANCO_ITEMS
    ]

    # ── Block 2 right: Per-share Values ──
    _PERSHARE_ITEMS = [
        ("LPA",  "lpa",  "brl_full", "Lucro por Ação = Lucro Líquido / total de ações"),
        ("VPA",  "vpa",  "brl_full", "Valor Patrimonial por Ação = PL / total de ações"),
        ("DPA",  "dpa",  "brl_full", "Dividendos por Ação = Dividendos pagos / total de ações"),
        ("RPA",  "rps",  "brl_full", "Receita por Ação = Receita Líquida / total de ações"),
    ]
    pershare_rows = [
        {"label": label, "value": _fmt(_safe_get(ratios_dict, key), spec)}
        for label, key, spec, tooltip in _PERSHARE_ITEMS
    ]

    sections.append({
        "type": "two_column",
        "left_title": "Balanço Patrimonial",
        "left_rows": balanco_rows,
        "right_title": "Valores por Ação",
        "right_rows": pershare_rows,
        "negative_red": True,
        "positive_green": True,
    })

    return sections


# ── V8: Radar chart — multidimensional valuation comparison ──────────────────

def build_valuation_radar(ratios_dict: dict | None) -> dict | None:
    """Build a radar chart comparing key valuation dimensions.

    Shows 6 axes: Valuation (inverse of P/L), Profitability (ROE), Growth
    (revenue_growth_1y), Liquidity (current_ratio), Leverage (inverse of
    D/E), and Margin (net_margin). All values are normalized to 0-100 scale
    so they fit on one radar.

    Returns a chart section dict, or None if fewer than 3 metrics are available.
    """
    if not isinstance(ratios_dict, dict):
        return None

    def _norm_pl(pl):
        """Normalize P/L to 0-100 (lower P/L = better = higher score)."""
        if pl is None or pl <= 0:
            return None
        # P/L of 5 = 100 (very cheap), P/L of 25 = 20 (expensive)
        return max(0, min(100, 100 - (pl - 5) * 4))

    def _norm_pct(val, max_val=0.5):
        """Normalize a percentage (fraction) to 0-100."""
        if val is None:
            return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_ratio(val, max_val=2.0):
        """Normalize a ratio to 0-100."""
        if val is None:
            return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_inverse(val, max_val=2.0):
        """Normalize inverse (lower = better): 100 - normalized."""
        if val is None:
            return None
        return max(0, 100 - min(100, (val / max_val) * 100))

    pl_score = _norm_pl(_safe_get(ratios_dict, "p_l"))
    roe_score = _norm_pct(_safe_get(ratios_dict, "roe"), 0.4)
    growth_score = _norm_pct(_safe_get(ratios_dict, "revenue_growth_1y"), 0.3)
    liq_score = _norm_ratio(_safe_get(ratios_dict, "current_ratio"), 3.0)
    lev_score = _norm_inverse(_safe_get(ratios_dict, "debt_equity"), 3.0)
    margin_score = _norm_pct(_safe_get(ratios_dict, "net_margin"), 0.3)

    scores = [pl_score, roe_score, growth_score, liq_score, lev_score, margin_score]
    if sum(1 for s in scores if s is not None) < 3:
        return None

    chart_data = {
        "type": "radar",
        "data": {
            "labels": ["Valoração", "Rentabilidade", "Crescimento", "Liquidez", "Alavancagem", "Margem"],
            "datasets": [{
                "label": "Score (0-100)",
                "data": scores,
                "borderColor": "#0d9488",
                "backgroundColor": "rgba(13,148,136,0.15)",
                "pointBackgroundColor": "#0d9488",
                "pointBorderColor": "#fff",
                "pointHoverBackgroundColor": "#fff",
                "pointHoverBorderColor": "#0d9488",
                "borderWidth": 2,
            }],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "r": {
                    "beginAtZero": True,
                    "max": 100,
                    "ticks": {"stepSize": 20},
                    "pointLabels": {"font": {"size": 12}},
                },
            },
            "plugins": {
                "legend": {"display": True, "position": "top"},
                "tooltip": {"mode": "index", "intersect": False},
            },
        },
    }

    return {
        "type": "chart",
        "title": "Radar de Valoração — Visão Multidimensional",
        "description": (
            "Score 0-100 por dimensão. Valoração: P/L inverso (menor = melhor). "
            "Rentabilidade: ROE. Crescimento: receita 1Y. Liquidez: corrente. "
            "Alavancagem: D/E inverso (menor = melhor). Margem: líquida."
        ),
        "chart_data": chart_data,
    }


# ── V9: Heatmap — valuation metrics color-coded ──────────────────────────────

def build_valuation_heatmap(ratios_dict: dict | None) -> dict | None:
    """Build a heatmap table of valuation metrics with color coding.

    Each metric is color-coded: green (good), yellow (neutral), red (bad).
    Colors are based on standard valuation thresholds.

    Returns a heatmap section dict, or None if no data available.
    """
    if not isinstance(ratios_dict, dict):
        return None

    _HEATMAP_TOOLTIPS = {
        "P/L": "Preço / Lucro por Ação. <10 barato, >25 caro.",
        "P/VPA": "Preço / Valor Patrimonial por Ação. <1 barato, >3 caro.",
        "EV/EBITDA": "Enterprise Value / EBITDA. <8 barato, >15 caro.",
        "ROE": "Lucro Líquido / PL. >20% bom, <10% ruim.",
        "ROIC": "NOPAT / Capital Investido. >12% bom, <7% ruim.",
        "Margem Líquida": "Lucro / Receita. >15% bom, <5% ruim.",
        "Margem EBITDA": "EBITDA / Receita. >25% bom, <10% ruim.",
        "D/E": "Dívida / PL. <0,5 bom, >2,0 ruim.",
        "Liquidez Corrente": "Ativo Circ / Passivo Circ. >1,5 bom, <1,0 ruim.",
        "Dividend Yield": "Dividendos / Preço. >5% bom, <2% ruim.",
    }

    def _heat(val, good_max, bad_max, reverse=False, tooltip=""):
        """Return {text, bg, color} based on value vs thresholds.
        reverse=True means lower is better (e.g. P/L)."""
        if val is None:
            return {"text": "—", "bg": "", "color": "", "tooltip": tooltip}
        if reverse:
            if val <= good_max:
                return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
            elif val <= bad_max:
                return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
            else:
                return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}
        else:
            if val >= good_max:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
            elif val >= bad_max:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
            else:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}

    def _heat_ratio(val, good_min, bad_min, tooltip=""):
        """For ratios where higher = better (e.g. current_ratio)."""
        if val is None:
            return {"text": "—", "bg": "", "color": "", "tooltip": tooltip}
        if val >= good_min:
            return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
        elif val >= bad_min:
            return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
        else:
            return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}

    rows = [
        ["P/L", _heat(_safe_get(ratios_dict, "p_l"), 10, 25, reverse=True, tooltip=_HEATMAP_TOOLTIPS["P/L"])],
        ["P/VPA", _heat(_safe_get(ratios_dict, "p_vpa"), 1.0, 3.0, reverse=True, tooltip=_HEATMAP_TOOLTIPS["P/VPA"])],
        ["EV/EBITDA", _heat(_safe_get(ratios_dict, "ev_ebitda"), 8, 15, reverse=True, tooltip=_HEATMAP_TOOLTIPS["EV/EBITDA"])],
        ["ROE", _heat(_safe_get(ratios_dict, "roe"), 0.20, 0.10, tooltip=_HEATMAP_TOOLTIPS["ROE"])],
        ["ROIC", _heat(_safe_get(ratios_dict, "roic"), 0.12, 0.07, tooltip=_HEATMAP_TOOLTIPS["ROIC"])],
        ["Margem Líquida", _heat(_safe_get(ratios_dict, "net_margin"), 0.15, 0.05, tooltip=_HEATMAP_TOOLTIPS["Margem Líquida"])],
        ["Margem EBITDA", _heat(_safe_get(ratios_dict, "ebitda_margin"), 0.25, 0.10, tooltip=_HEATMAP_TOOLTIPS["Margem EBITDA"])],
        ["D/E", _heat(_safe_get(ratios_dict, "debt_equity"), 0.5, 2.0, reverse=True, tooltip=_HEATMAP_TOOLTIPS["D/E"])],
        ["Liquidez Corrente", _heat_ratio(_safe_get(ratios_dict, "current_ratio"), 1.5, 1.0, tooltip=_HEATMAP_TOOLTIPS["Liquidez Corrente"])],
        ["Dividend Yield", _heat(_safe_get(ratios_dict, "dividend_yield"), 0.05, 0.02, tooltip=_HEATMAP_TOOLTIPS["Dividend Yield"])],
    ]

    return {
        "type": "heatmap",
        "title": "Heatmap de Valoração — Indicadores Coloridos",
        "description": (
            "Verde = bom, Amarelo = neutro, Vermelho = ruim. "
            "Thresholds baseados em práticas de valuation para B3."
        ),
        "columns": ["Métrica", "Valor"],
        "rows": rows,
    }
