"""report/liquidity.py — Liquidity & Leverage tab builder.

Contains:
  - build_liquidity_leverage_sections — split Liquidity + Leverage ratio_grids
    + Working Capital BRL table + Detailed Leverage table
"""
from __future__ import annotations

from skills.cvm.valuation.report._helpers import (
    _safe_get, _fmt, _derive_detailed_leverage,
)
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── Tab 5: Liquidity & Leverage -- ratio_grid + collapsible ──────────────────

_LIQUIDITY_ITEMS: list[tuple[str, str, str]] = [
    ("Current Ratio",    "current_ratio",    "num"),
    ("Quick Ratio",      "quick_ratio",      "num"),
    ("Cash Ratio",       "cash_ratio",       "num"),
    # [v1.9] Working Capital removed from this list — it's a BRL value, not a
    # ratio, so it gets its own BRL section below the Liquidity ratio_grid.
]

_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    ("Debt/Equity",         "debt_equity",       "pct"),
    ("Net Debt/EBITDA",     "net_debt_ebitda",   "num"),
    ("Financial Leverage",  "financial_leverage","num"),
    ("Interest Coverage",   "interest_coverage", "num"),
    ("Cash Flow to Debt",   "cash_flow_to_debt", "pct"),
]

# Detailed leverage metrics (collapsible). DL = Dívida Líquida.
_DETAILED_LEVERAGE_ITEMS: list[tuple[str, str, str]] = [
    ("DL/EBIT",    "net_debt_ebit",    "num"),
    ("DL/EBITDA",  "net_debt_ebitda",  "num"),
    ("Gross Debt/Equity", "gross_debt_equity", "pct"),
]


def build_liquidity_leverage_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Liquidity & Leverage tab — split ratio_grids + charts + detailed table.

    [v1.9] Split into separate Liquidity and Leverage ratio_grids so the
    dashboard can group them under "Liquidez" and "Endividamento" subtabs.
    Working Capital (BRL, not a ratio) is now its own BRL section below the
    Liquidity ratio_grid. Returns 6 sections in order:
      [0] Liquidity ratio_grid (3 items, no Working Capital)
      [1] Working Capital BRL table (1 row)
      [2] Liquidity chart
      [3] Leverage ratio_grid (5 items)
      [4] Leverage chart
      [5] Detailed Leverage table
    """
    sections: list[dict] = []

    # ── Liquidity ratio_grid (no Working Capital) ──
    liquidity_items = []
    for label, key, spec in _LIQUIDITY_ITEMS:
        raw = _safe_get(ratios_dict, key)
        liquidity_items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
        })
    sections.append({
        "title": "Liquidez",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Liquidity", "items": liquidity_items},
        ],
    })

    # ── Working Capital BRL section (separate — it's a BRL value, not a ratio) ──
    wc_raw = _safe_get(ratios_dict, "working_capital")
    sections.append({
        "title": "Capital de Giro (BRL)",
        "description": "Ativo Circulante - Passivo Circulante. Valor em BRL.",
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": [[
            {"text": "Working Capital", "tooltip": _get_tooltip("working_capital")},
            _fmt(wc_raw, "brl"),
        ]],
    })

    # ── Leverage ratio_grid ──
    leverage_items = []
    for label, key, spec in _LEVERAGE_ITEMS:
        raw = _safe_get(ratios_dict, key)
        leverage_items.append({
            "label": label,
            "value": _fmt(raw, spec),
            "value_raw": float(raw) if raw is not None else None,
            "tooltip": _get_tooltip(key),
        })
    sections.append({
        "title": "Alavancagem",
        "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
        "type": "ratio_grid",
        "categories": [
            {"label": "Leverage", "items": leverage_items},
        ],
    })

    # [v1.8] Chart 1: Liquidity ratios
    liq_labels = [i["label"] for i in liquidity_items if i.get("value_raw") is not None]
    liq_values = [i["value_raw"] for i in liquidity_items if i.get("value_raw") is not None]
    if len(liq_labels) >= 2:
        sections.insert(2, {
            "type": "chart",
            "title": "Liquidez — Comparativo",
            "description": "Liquidez Corrente, Seca, Imediata.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": liq_labels,
                         "datasets": [{"label": "Liquidez", "data": liq_values,
                                       "backgroundColor": "#3b82f6"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # [v1.8] Chart 2: Leverage ratios
    lev_labels = [i["label"] for i in leverage_items if i.get("value_raw") is not None]
    lev_values = [i["value_raw"] for i in leverage_items if i.get("value_raw") is not None]
    if len(lev_labels) >= 2:
        lev_pct = [v * 100 if abs(v) < 1 else v for v in lev_values]
        sections.append({
            "type": "chart",
            "title": "Alavancagem — Comparativo",
            "description": "Dívida/PL, Dív.Líq/EBITDA, Alavancagem Financeira, Cobertura Juros, FCO/Dívida.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": lev_labels,
                         "datasets": [{"label": "Alavancagem", "data": lev_pct,
                                       "backgroundColor": "#ef4444"}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # [v1.8] Detailed Leverage — table (was collapsible).
    derived = _derive_detailed_leverage(ratios_dict)
    detail_rows = []
    for label, key, spec in _DETAILED_LEVERAGE_ITEMS:
        value = _safe_get(ratios_dict, key)
        if value is None:
            value = derived.get(key)
        interp = ""
        if key == "net_debt_ebit" and value is not None:
            interp = "Baixa alavancagem" if value < 2 else "Alta alavancagem" if value > 4 else "Alavancagem moderada"
        elif key == "net_debt_ebitda" and value is not None:
            interp = "Baixa" if value < 2 else "Alta" if value > 3 else "Moderada"
        elif key == "gross_debt_equity" and value is not None:
            interp = "Baixa" if value < 0.3 else "Alta" if value > 0.6 else "Moderada"
        formula = _get_tooltip(key) or _get_tooltip("dl_ebit" if key == "net_debt_ebit" else key)
        if not formula:
            formula = f"{label} = (Dívida Bruta - Caixa) / EBIT" if "ebit" in key and "ebitda" not in key else f"{label} = Dívida Bruta / PL"
        detail_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Alavancagem Detalhada",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": detail_rows,
    })

    return sections
