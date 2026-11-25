"""report/multiples.py — Multiples + Per-share tab builders.

Contains:
  - build_multiples_sections   — 3 grouped tables (Price / EV / Less Common)
                                 + per-group bar charts
  - build_per_share_sections   — per-share BRL values table + bar chart
"""
from __future__ import annotations

from typing import Any

from skills.cvm.valuation.report._helpers import (
    _safe_get, _fmt, _safe_div,
    _derive_multiples, _derive_per_share,
    _MULTIPLES_LESS_COMMON, _PER_SHARE_ITEMS,
)
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


def build_multiples_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Multiples tab sections — split by group.

    [v1.8] Split the single top-10 table into 3 grouped tables:
      1. Múltiplos de Preço (P/L, P/VPA, P/EBIT, P/EBITDA, PSR, P/FCO, P/FCF)
      2. Múltiplos EV (EV/EBIT, EV/EBITDA, EV/Sales, EV/FCF, P/EV)
      3. Menos Comuns (P/Ativos, P/Passivos, P/RB, P/CG, P/DB, P/Tangible Book)
    Each group has its own bar chart. Less Common is now a table (was collapsible).
    """
    sections: list[dict] = []
    derived = _derive_multiples(ratios_dict)

    def _lookup(key: str) -> Any:
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    # ── Group 1: Múltiplos de Preço ──
    # [v2.1] P/EBIT and P/EBITDA moved to the EBIT/EBITDA subtab.
    _PRICE_MULTIPLES = [
        ("P/L",       "p_l",       "num", "Cheap if < 10; expensive if > 25",  _get_tooltip("lpa")),
        ("P/VPA",     "p_vpa",     "num", "Cheap if < 1; expensive if > 3",    _get_tooltip("vpa")),
        ("PSR",       "psr",       "num", "Cheap if < 1; expensive if > 3",    _get_tooltip("rps")),
        ("P/FCO",     "p_fco",     "num", "Cheap if < 10; expensive if > 25",  _get_tooltip("p_fco")),
        ("P/FCF",     "p_fcf",     "num", "Cheap if < 15; expensive if > 30",  _get_tooltip("p_fcf")),
    ]
    price_rows = []
    price_chart_labels = []
    price_chart_values = []
    for label, key, spec, interp, formula in _PRICE_MULTIPLES:
        value = _lookup(key)
        price_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
        if value is not None:
            price_chart_labels.append(label)
            price_chart_values.append(float(value))
    sections.append({
        "title": "Múltiplos de Preço",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": price_rows,
        "negative_red": True,
        "positive_green": True,
    })
    if len(price_chart_labels) >= 2:
        sections.append({
            "type": "chart",
            "title": "Múltiplos de Preço — Comparativo",
            "description": "P/L, P/VPA, PSR, P/FCO, P/FCF. Menor = mais barato.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": price_chart_labels,
                    "datasets": [{"label": "Preço", "data": price_chart_values,
                                  "backgroundColor": "#3b82f6"}],
                },
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # ── Group 2: Múltiplos EBIT ──
    # [v2.1] New EBIT table: P/EBIT, EV/EBIT, DL/EBIT side-by-side.
    _EBIT_MULTIPLES = [
        ("P/EBIT",    "p_ebit",    "num", "Cheap if < 8; expensive if > 20",   _get_tooltip("p_ebit")),
        ("EV/EBIT",   "ev_ebit",   "num", "Cheap if < 8; expensive if > 15",   _get_tooltip("ev_ebit")),
        ("DL/EBIT",   "dl_ebit",   "num", "Dívida Líquida / EBIT. <2 baixa, >4 alta", _get_tooltip("dl_ebit")),
    ]
    ebit_rows = []
    for label, key, spec, interp, formula in _EBIT_MULTIPLES:
        value = _lookup(key)
        ebit_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Múltiplos EBIT",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": ebit_rows,
        "negative_red": True,
        "positive_green": True,
    })

    # ── Group 3: Múltiplos EBITDA ──
    # [v2.1] New EBITDA table: P/EBITDA, EV/EBITDA, DL/EBITDA side-by-side.
    _EBITDA_MULTIPLES = [
        ("P/EBITDA",  "p_ebitda",  "num", "Cheap if < 8; expensive if > 15",   _get_tooltip("p_ebitda")),
        ("EV/EBITDA", "ev_ebitda", "num", "Cheap if < 8; expensive if > 15",   _get_tooltip("ev_ebitda")),
        ("DL/EBITDA", "net_debt_ebitda", "num", "Dívida Líq / EBITDA. <1.5 baixa, >3.5 alta", _get_tooltip("net_debt_ebitda")),
    ]
    ebitda_rows = []
    for label, key, spec, interp, formula in _EBITDA_MULTIPLES:
        value = _lookup(key)
        ebitda_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
    sections.append({
        "title": "Múltiplos EBITDA",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": ebitda_rows,
        "negative_red": True,
        "positive_green": True,
    })

    # ── Group 4: Múltiplos EV ──
    # [v2.1] EV/EBIT + EV/EBITDA moved to EBIT/EBITDA tables above. EV
    # subtab keeps EV/Sales, EV/FCF, P/EV — the EV-specific multiples.
    _EV_MULTIPLES = [
        ("EV/Sales",  "ev_sales",  "num", "Cheap if < 1; expensive if > 3",   _get_tooltip("ev_sales")),
        ("EV/FCF",    "ev_fcf",    "num", "Cheap if < 10; expensive if > 25", _get_tooltip("ev_fcf")),
        ("P/EV",      "p_ev",      "num", "Cheap if < 1; expensive if > 3",   _get_tooltip("p_ev")),
    ]
    ev_rows = []
    ev_chart_labels = []
    ev_chart_values = []
    for label, key, spec, interp, formula in _EV_MULTIPLES:
        value = _lookup(key)
        ev_rows.append([{"text": label, "tooltip": formula}, _fmt(value, spec), interp if value is not None else "—"])
        if value is not None:
            ev_chart_labels.append(label)
            ev_chart_values.append(float(value))
    sections.append({
        "title": "Múltiplos EV (Enterprise Value)",
        "type": "table",
        "columns": ["Métrica", "Valor", "Interpretação"],
        "rows": ev_rows,
        "negative_red": True,
        "positive_green": True,
    })
    if len(ev_chart_labels) >= 2:
        sections.append({
            "type": "chart",
            "title": "Múltiplos EV — Comparativo",
            "description": "EV/EBIT, EV/EBITDA, EV/Sales, EV/FCF. Menor = mais barato.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": ev_chart_labels,
                    "datasets": [{"label": "EV", "data": ev_chart_values,
                                  "backgroundColor": "#f59e0b"}],
                },
                "options": {"responsive": True, "maintainAspectRatio": False,
                            "scales": {"y": {"beginAtZero": True}}},
            },
        })

    # ── Group 3: Menos Comuns (heatmap) ──
    # [v1.26.1] Was a plain table — now the same colored-indicator
    # presentation as the Histórico tab's "Heatmap de Valoração —
    # Indicadores Coloridos": each row's Valor + Leitura cells carry the
    # verdict color (green = lado favorável, âmbar = faixa média,
    # vermelho = lado desfavorável). Bands are indicative (the same
    # "cheap if / expensive if" reading the old Interpretação column
    # spelled out, now encoded in color + a one-word Leitura).
    sections.append(_build_less_common_heatmap(ratios_dict, derived))

    return sections


# Heatmap cell colors — the valuation heatmap palette
# (skills/cvm/valuation/report/overview.py).
_HC_GOOD = ("rgba(34,197,94,0.2)", "#16a34a")
_HC_MID = ("rgba(245,158,11,0.2)", "#d97706")
_HC_BAD = ("rgba(220,38,38,0.2)", "#dc2626")

# key → (direction, good_bound, bad_bound, good_label, mid_label, bad_label)
#   direction "low":  value ≤ good_bound → good; ≤ bad_bound → mid; else bad
#   direction "high": value ≥ good_bound → good; ≥ bad_bound → mid; else bad
# Bands mirror the interpretation text each row used to carry.
_LESS_COMMON_BANDS = {
    "apa": ("low", 1.0, 2.0, "Barata", "Na faixa", "Cara"),
    "ppa": ("low", 1.0, 3.0, "Pouco alavancado", "Alavancagem média",
            "Muito alavancado"),
    "rbpa": ("low", 1.0, 3.0, "Barata", "Na faixa", "Cara"),
    "p_cg": ("low", 2.0, 6.0, "Barata", "Na faixa", "Cara"),
    "p_db": ("low", 5.0, 15.0, "Barata", "Na faixa", "Cara"),
    "price_to_tangible_book": ("low", 1.0, 3.0, "Barata", "Na faixa", "Cara"),
    "a_p_inverse": ("high", 1.0, 0.5, "Favorável", "Faixa média",
                    "Desfavorável"),
    "financial_leverage": ("low", 1.5, 3.0, "Alavancagem baixa",
                           "Alavancagem média", "Alavancagem alta"),
    "p_vpa": ("low", 1.0, 3.0, "Barata", "Na faixa", "Cara"),
}


def _build_less_common_heatmap(ratios_dict: dict | None,
                               derived: dict) -> dict:
    """'Múltiplos Menos Comuns' as a colored heatmap section.

    Columns: Métrica (formula tooltip) | Valor (colored) | Leitura
    (colored one-word verdict). Rows with no value keep the "—" cell
    (uncolored) — absence is not a verdict.
    """

    def _lookup(key: str) -> Any:
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    rows: list[list[Any]] = []
    for label, key, spec, interp in _MULTIPLES_LESS_COMMON:
        value = _lookup(key)
        formula = _get_tooltip(key) or _get_tooltip(key.replace("_", ""))
        metric_cell: Any = {"text": label, "tooltip": formula}
        if value is None:
            rows.append([metric_cell,
                         {"text": "—", "bg": "", "color": ""},
                         {"text": "—", "bg": "", "color": ""}])
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = None
        band = _LESS_COMMON_BANDS.get(key)
        if num is not None and band:
            direction, good_b, bad_b, good_l, mid_l, bad_l = band
            if direction == "low":
                bg, fg, verdict = (( *_HC_GOOD, good_l) if num <= good_b
                                    else ((*_HC_MID, mid_l) if num <= bad_b
                                          else (*_HC_BAD, bad_l)))
            else:
                bg, fg, verdict = (( *_HC_GOOD, good_l) if num >= good_b
                                    else ((*_HC_MID, mid_l) if num >= bad_b
                                          else (*_HC_BAD, bad_l)))
            value_cell = {"text": _fmt(value, spec), "bg": bg, "color": fg}
            verdict_cell = {"text": verdict, "bg": bg, "color": fg,
                            "tooltip": interp}
        else:
            value_cell = {"text": _fmt(value, spec), "bg": "", "color": ""}
            verdict_cell = {"text": "—", "bg": "", "color": "",
                            "tooltip": interp}
        rows.append([metric_cell, value_cell, verdict_cell])

    return {
        "title": "Múltiplos Menos Comuns",
        "type": "heatmap",
        "description": (
            "Múltiplos de balanço menos observados, com leitura colorida: "
            "verde = lado favorável da faixa · âmbar = faixa média · "
            "vermelho = lado desfavorável. Faixas indicativas (setoriais "
            "divergem) — pare o mouse na métrica para a fórmula."
        ),
        "columns": ["Métrica", "Valor", "Leitura"],
        "rows": rows,
    }


def build_per_share_sections(ratios_dict: dict | None) -> list[dict]:
    """Build the Per-share tab sections: table + bar chart.

    Table columns: [Métrica, Valor (R$), Preço/Valor]
    The Preço/Valor column shows the price multiple (price / per-share value)
    where one is known (P/L for LPA, P/VPA for VPA, PSR for RPA); otherwise
    we compute it locally as price / per_share_value when both are present.
    """
    sections: list[dict] = []
    derived = _derive_per_share(ratios_dict)

    price = _safe_get(ratios_dict, "price")

    def _lookup(key: str) -> Any:
        v = _safe_get(ratios_dict, key)
        if v is None:
            v = derived.get(key)
        return v

    rows: list[list[str]] = []
    chart_labels: list[str] = []
    chart_data: list[float | None] = []

    for label, value_key, ratio_key in _PER_SHARE_ITEMS:
        value = _lookup(value_key)
        # Compute the price-multiple ratio.
        if ratio_key:
            ratio_value = _lookup(ratio_key)
        else:
            # Compute price / value locally.
            ratio_value = _safe_div(price, value)
        # [v1.8] Add tooltip/formula column.
        formula = _get_tooltip(value_key) or f"{label} = valor total / total de ações"
        rows.append([{"text": label, "tooltip": formula}, _fmt(value, "brl_full"), _fmt(ratio_value, "num")])
        # Collect for chart (skip DPA — usually much smaller than LPA/VPA/RPA;
        # but include for completeness).
        chart_labels.append(label)
        chart_data.append(value)

    sections.append({
        "title": "Per-share Values (R$)",
        "type": "table",
        "columns": ["Métrica", "Valor (R$)", "Preço/Valor"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
        "note": (
            "Per-share BRL values + the corresponding price multiple. "
            "RBPA / APA / PPA require engines not yet wired (see ROADMAP) — "
            "shown as '—'."
        ),
    })

    # ── Bar chart: per-share values side-by-side ──
    if any(v is not None for v in chart_data):
        sections.append({
            "type": "chart",
            "title": "Valores por Ação — Comparativo",
            "description": "LPA, VPA, DPA, RPS e derivados. Mostra o valor por ação de cada métrica.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": chart_labels,
                    "datasets": [{
                        "label": "Per-share (R$)",
                        "data": [v if v is not None else 0 for v in chart_data],
                        "backgroundColor": "#3b82f6",
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "scales": {
                        "y": {"beginAtZero": True},
                    },
                    "plugins": {
                        "legend": {"display": False},
                    },
                },
            },
        })

    return sections
