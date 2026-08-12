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
    """Build the Overview tab sections: split metrics into 3 related tables.

    [v1.8] Removed Price Details collapsible (price info is in the company
    header now). Split the single Key Metrics table into 3 grouped tables:
      1. Métricas de Mercado (market-cap-based: P/L, P/VPA, EV/EBITDA, etc.)
      2. Resultado (income statement: Receita, EBITDA, Lucro Líquido, etc.)
      3. Balanço (balance sheet: Ativo Total, PL, Dívida, Caixa)
    """
    sections: list[dict] = []

    # ── Table 1: Métricas de Mercado ──
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
    sections.append({
        "title": "Métricas de Mercado",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _MERCADO_ITEMS
        ],
    })

    # ── Table 2: Resultado ──
    _RESULTADO_ITEMS = [
        ("Receita Líquida",    "receita_liquida",    "brl", "Receita total após deduções (DRE 3.01)"),
        ("EBITDA",             "ebitda",             "brl", "EBIT + D&A (Depreciação e Amortização)"),
        ("Lucro Líquido",      "lucro_liquido",      "brl", "Lucro/Prejuízo Consolidado (DRE 3.11)"),
        ("ROE",                "roe",                "pct", _get_tooltip("roe")),
        ("ROA",                "roa",                "pct", _get_tooltip("roa")),
        ("ROIC",               "roic",               "pct", _get_tooltip("roic")),
    ]
    sections.append({
        "title": "Resultado (TTM)",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _RESULTADO_ITEMS
        ],
    })

    # ── Table 3: Balanço ──
    _BALANCO_ITEMS = [
        ("Patrimônio Líquido", "patrimonio_liquido", "brl", "Capital próprio dos acionistas (BPP 2.03)"),
        ("Dívida Bruta",       "divida_bruta",       "brl", "Empréstimos Circ + Não Circ (2.01.04 + 2.02.01)"),
        ("Caixa",              "caixa",              "brl", "Caixa e Equivalentes (BPA 1.01.01)"),
        ("Total de Ações",     "total_shares",       "int", "Total de ações outstanding (FRE)"),
    ]
    sections.append({
        "title": "Balanço Patrimonial",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [
            [{"text": label, "tooltip": tooltip}, _fmt(_safe_get(ratios_dict, key), spec)]
            for label, key, spec, tooltip in _BALANCO_ITEMS
        ],
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

    def _heat(val, good_max, bad_max, reverse=False):
        """Return {text, bg, color} based on value vs thresholds.
        reverse=True means lower is better (e.g. P/L)."""
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if reverse:
            if val <= good_max:
                return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val <= bad_max:
                return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}
        else:
            if val >= good_max:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val >= bad_max:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    def _heat_ratio(val, good_min, bad_min):
        """For ratios where higher = better (e.g. current_ratio)."""
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if val >= good_min:
            return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
        elif val >= bad_min:
            return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
        else:
            return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    rows = [
        ["P/L", _heat(_safe_get(ratios_dict, "p_l"), 10, 25, reverse=True)],
        ["P/VPA", _heat(_safe_get(ratios_dict, "p_vpa"), 1.0, 3.0, reverse=True)],
        ["EV/EBITDA", _heat(_safe_get(ratios_dict, "ev_ebitda"), 8, 15, reverse=True)],
        ["ROE", _heat(_safe_get(ratios_dict, "roe"), 0.20, 0.10)],
        ["ROIC", _heat(_safe_get(ratios_dict, "roic"), 0.12, 0.07)],
        ["Margem Líquida", _heat(_safe_get(ratios_dict, "net_margin"), 0.15, 0.05)],
        ["Margem EBITDA", _heat(_safe_get(ratios_dict, "ebitda_margin"), 0.25, 0.10)],
        ["D/E", _heat(_safe_get(ratios_dict, "debt_equity"), 0.5, 2.0, reverse=True)],
        ["Liquidez Corrente", _heat_ratio(_safe_get(ratios_dict, "current_ratio"), 1.5, 1.0)],
        ["Dividend Yield", _heat(_safe_get(ratios_dict, "dividend_yield"), 0.05, 0.02)],
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
