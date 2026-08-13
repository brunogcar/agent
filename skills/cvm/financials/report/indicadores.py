"""skills/cvm/financials/report/indicadores.py -- Indicadores tab builders.

Builds the "Indicadores" tab (ratio_grid of all ratio categories with
per-group bar charts) plus the growth ratio_grid helper used by the
Crescimento tab.

Public builders:
  - ``build_indicadores_section(today, ratios_payload)`` — top-level subtabs
    section with "Todas" + per-category subtabs.

Private helpers (also imported by ``report/crescimento.py``):
  - ``_group_metrics_by_prefix(items, category_label)`` — splits items into
    box groups by metric-name prefix (EV/, P/, Marg., etc.).
  - ``_build_category_items(category, ratios_payload)`` — builds items list
    for a single category from the calculations registry.
  - ``_build_group_bar_chart(gname, gitems, category)`` — bar chart for one
    box group.
  - ``_build_growth_ratio_grid_section(ratios_payload, today)`` — ratio_grid
    section showing all growth metrics (moved from Indicadores in v1.25).
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import (
    _fmt,
    _get_tooltip,
    _METRIC_LABELS,
    _RATIO_PCT_KEYS,
    _INDICADORES_EXCLUDE,
    _RATIO_CATEGORY_LABELS,
    _INDICADORES_CATEGORIES,
    _VALUATION_CHART_EXCLUDE,
    _GROUP_CHART_COLORS,
    _VALUATION_CHART_TITLES,
    _VALUATION_CHART_DESCRIPTIONS,
)


def _group_metrics_by_prefix(items: list[dict], category_label: str = "") -> list[dict]:
    """Group metric items by their label prefix (EV/, P/, ROE, etc.).

    Items with labels starting with "EV/" go into "EV (Enterprise Value)".
    Items with labels starting with "P/" go into "P/ (Price)".
    Growth items split by underlying metric (Receita/Lucro Líq./Resultado Bruto).
    CAGR items join the same per-metric group as their simple-growth siblings.
    Leverage items (category_label == "Endividamento") are split into
    "Ratios" (D/E, FCO/Dívida, Dív. Bruta/PL, Alavancagem Financeira) and
    "Multiples/Coverage" (Dív. Líq/EBITDA, DL/EBIT, Cobertura de Juros,
    Altman Z-Score) so they get separate charts with similar y-axis scales.
    Everything else goes into a group named after the category_label
    (e.g. "Liquidez", "Tributos") instead of the generic "Outros".

    [new commit] The "Outros" bucket is named after the category_label
    parameter (e.g. "Liquidez", "Endividamento", "Tributos"). User feedback:
    "box Outros - should be liquidez". For growth, keeps "Outros Crescimento".

    [v1.25] Added CAGR grouping (CAGR Receita/Lucro/Resultado Bruto join
    the matching simple-growth group), leverage 2-way split, and ROI in
    the Retorno group. Items must carry a "metric_name" field for the
    leverage split (other branches fall back to label-only matching).
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        label = item.get("label", "")
        metric_name = item.get("metric_name", "")
        if label.startswith("EV/"):
            gname = "EV (Enterprise Value)"
        elif label.startswith("P/"):
            gname = "P/ (Price)"
        elif label.startswith("Marg."):
            gname = "Margens"
        elif label.startswith("Giro"):
            gname = "Giro"
        elif label in ("ROE", "ROA", "ROIC", "ROI"):
            gname = "Retorno"
        elif (label.startswith("Crescimento Receita")
              or label.startswith("CAGR Receita")):
            gname = "Receita"
        elif (label.startswith("Crescimento Lucro")
              or label.startswith("CAGR Lucro")):
            gname = "Lucro Líquido"
        elif (label.startswith("Crescimento Resultado")
              or label.startswith("CAGR Resultado")):
            gname = "Resultado Bruto"
        elif label.startswith("Crescimento") or label.startswith("CAGR"):
            gname = "Outros Crescimento"
        elif category_label == "Endividamento":
            # [v1.25] Split leverage into "Ratios" and "Multiples/Coverage"
            # so each gets its own chart with a sensible y-axis range.
            # Ratios  → 0-2 range (D/E, FCO/Dívida, Dív. Bruta/PL, Alavancagem).
            # Multiples → 0-10+ range (Dív.Líq/EBITDA, DL/EBIT, Cobertura, Altman).
            if metric_name in {"debt_equity", "cash_flow_to_debt",
                               "gross_debt_equity", "financial_leverage"}:
                gname = "Ratios"
            else:
                gname = "Multiples/Coverage"
        else:
            # [new commit] Use the category label instead of generic "Outros"
            gname = category_label if category_label else "Outros"
        groups.setdefault(gname, []).append(item)

    # [v2.1 v3] Sort items WITHIN each growth group.
    # User wants grouped by type: all Crescimento first (3M/1A/5A), then all CAGR (3M/1A/5A).
    # NOT alternating (Crescimento 3M, CAGR 3M, Crescimento 1A, ...).
    _GROWTH_HORIZON_ORDER = {
        "3M": 0, "1A": 1, "5A": 2, "1Y": 1, "5Y": 2,
    }
    growth_groups = {"Receita", "Lucro Líquido", "Resultado Bruto",
                     "Outros Crescimento"}
    for gname in growth_groups:
        if gname in groups:
            def _horizon_key(item: dict) -> tuple:
                lbl = item.get("label", "")
                # Primary key: Crescimento (0) before CAGR (1)
                is_cagr = 1 if lbl.startswith("CAGR") else 0
                # Secondary key: horizon (3M=0, 1A=1, 5A=2)
                horizon = 99
                for tok, key in _GROWTH_HORIZON_ORDER.items():
                    if lbl.endswith(" " + tok) or lbl.endswith(tok):
                        horizon = key
                        break
                return (is_cagr, horizon)
            groups[gname].sort(key=_horizon_key)

    # Return in a sensible order
    order = [
        "EV (Enterprise Value)", "P/ (Price)", "Retorno", "Margens",
        "Giro", "Ratios", "Multiples/Coverage",
        "Receita", "Lucro Líquido", "Resultado Bruto",
        "Outros Crescimento", "Outros",
    ]
    result = []
    for gname in order:
        if gname in groups:
            result.append({"label": gname, "items": groups[gname]})
    # Add any groups not in the order list (preserves insertion order)
    for gname, gitems in groups.items():
        if gname not in order:
            result.append({"label": gname, "items": gitems})
    return result


def _build_category_items(category: str, ratios_payload: dict) -> tuple[list[dict], str | None]:
    """[v1.25] Build a list of ratio_grid items for a single category.

    Returns ``(items, cat_label)`` where each item has keys:
    ``label``, ``value``, ``value_raw``, ``metric_name``, ``tooltip``.
    Returns ``([], None)`` when the category has no plottable metrics.

    Used by both ``build_indicadores_section`` (per-category subtabs +
    "Todas" subtab) and ``build_crescimento_sections`` (growth ratio_grid
    moved out of Indicadores in v1.25).
    """
    try:
        from skills.cvm.calculations._registry import (
            METRICS, list_metrics_by_category,
        )
    except Exception:
        return [], None
    metrics_in_cat = list_metrics_by_category(category)
    if not metrics_in_cat:
        return [], None
    items: list[dict] = []
    for metric_name in metrics_in_cat:
        # Exclude raw-number metrics (working_capital) — they're not ratios.
        if metric_name in _INDICADORES_EXCLUDE:
            continue
        spec = METRICS.get(metric_name)
        if not spec:
            continue
        value = ratios_payload.get(metric_name)
        fmt_spec = "pct" if metric_name in _RATIO_PCT_KEYS else "num"
        label = _METRIC_LABELS.get(metric_name, spec.ratio_label)
        tooltip = _get_tooltip(metric_name, spec)
        items.append({
            "label": label,
            "value": _fmt(value, fmt_spec),
            # [v1.16.1] Store raw numeric value for chart builders.
            # Avoids fragile parsing of formatted strings (PT-BR "1.234,56"
            # breaks float() — was a P0 bug).
            "value_raw": float(value) if value is not None else None,
            # [v1.25] metric_name kept on the item so _group_metrics_by_prefix
            # can split leverage into Ratios/Multiples, and so valuation
            # charts can exclude BRL-value metrics (dcf_intrinsic_value,
            # graham_number).
            "metric_name": metric_name,
            "tooltip": tooltip,
        })
    if not items:
        return [], None
    cat_label = _RATIO_CATEGORY_LABELS.get(category, category.capitalize())
    return items, cat_label


def _build_group_bar_chart(
    gname: str, gitems: list[dict], category: str = "",
) -> dict | None:
    """[v1.25] Build a bar chart for a single ratio_grid box group.

    Scales 0-1 fractions to 0-100 percentages for display (using
    ``_RATIO_PCT_KEYS`` as the source of truth — more reliable than the
    previous ``abs(raw) < 1`` heuristic that mis-scaled growth values
    like 1.5 = 150%).

    Returns ``None`` when no plottable items (all values None).

    For valuation, the chart title comes from ``_VALUATION_CHART_TITLES``
    and the description from ``_VALUATION_CHART_DESCRIPTIONS`` — both
    honor the 3-group split the user named explicitly in the v1.25 spec
    (EV / P/ / Indicadores de Valor).
    """
    chart_labels: list[str] = []
    chart_values: list[float] = []
    for item in gitems:
        raw = item.get("value_raw")
        if raw is None:
            continue
        # Scale fractions (0-1) to percentages (0-100) for chart display.
        # Use _RATIO_PCT_KEYS as the source of truth (handles values >1.0
        # like 150% growth that the abs(raw) < 1 heuristic missed).
        metric_name = item.get("metric_name", "")
        if metric_name in _RATIO_PCT_KEYS:
            raw = raw * 100
        chart_labels.append(item["label"])
        chart_values.append(raw)
    if not chart_labels:
        return None

    color = _GROUP_CHART_COLORS.get(gname, "#0d9488")
    if category == "valuation":
        chart_title = _VALUATION_CHART_TITLES.get(gname, gname)
        chart_desc = _VALUATION_CHART_DESCRIPTIONS.get(
            gname, f"Valores numéricos: {gname}.")
    else:
        chart_title = gname
        chart_desc = f"Valores numéricos: {gname}."

    return {
        "type": "chart",
        "title": chart_title,
        "description": chart_desc,
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": chart_labels,
                "datasets": [{
                    "label": gname,
                    "data": chart_values,
                    "backgroundColor": color,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {}}},
                "plugins": {
                    "title": {"display": True, "text": chart_title},
                },
            },
        },
    }


def build_indicadores_section(today: str, ratios_payload: dict) -> dict:
    """Build the Indicadores tab as a ``type: "subtabs"`` section.

    [v1.16] First sub-tab "Todas" shows ALL categories in one ratio_grid.
    Then individual category sub-tabs follow, each with items sub-grouped
    by prefix (EV/, P/, Retorno, Margens, etc.) within the ratio_grid.

    [v1.18] Each category subtab now also includes a bar chart showing
    the numeric values of that category's metrics — visual comparison
    alongside the ratio_grid.

    [v1.25] Charts split per ratio_grid box group (one chart per group,
    not one giant chart per category). Valuation gets 3 charts (EV / P/
    / Indicadores de Valor), excluding DCF Intrinsic + Graham Number
    (BRL values that break the y-axis scale). Growth subtab removed —
    moved to the dedicated Crescimento tab.
    """
    sub_tabs: list[dict] = []

    # First sub-tab: "Todas" — all categories in one ratio_grid.
    all_cats: list[dict] = []
    for category in _INDICADORES_CATEGORIES:
        items, cat_label = _build_category_items(category, ratios_payload)
        if items:
            all_cats.append({"label": cat_label, "items": items})
    if all_cats:
        sub_tabs.append({
            "name": "Todas",
            "sections": [{
                "title": f"Todos os Indicadores (as of {today})",
                "description": "Passe o mouse sobre cada indicador para ver a fórmula e explicação (ⓘ).",
                "type": "ratio_grid",
                "categories": all_cats,
            }],
        })

    # Individual category sub-tabs with prefix sub-grouping + per-group charts.
    for category in _INDICADORES_CATEGORIES:
        items, cat_label = _build_category_items(category, ratios_payload)
        if not items:
            continue
        # For valuation, the else bucket is "Indicadores de Valor" so the
        # 3 groups are: EV / P/ / Indicadores de Valor (matches the chart
        # titles the user named in the v1.25 spec).
        if category == "valuation":
            grouped = _group_metrics_by_prefix(
                items, category_label="Indicadores de Valor")
        else:
            grouped = _group_metrics_by_prefix(items, category_label=cat_label)

        sub_sections: list[dict] = [{
            "title": f"{cat_label} (as of {today})",
            "description": "Passe o mouse sobre cada indicador para ver a fórmula (ⓘ).",
            "type": "ratio_grid",
            "categories": grouped,
        }]

        # [v1.25] One chart per group (split by box groups, not one
        # giant chart per category). For valuation, exclude BRL-value
        # metrics (DCF Intrinsic + Graham Number) from charts — they
        # break the y-axis scale (R$ tens vs ratio multiples).
        for group in grouped:
            gname = group["label"]
            gitems = group["items"]
            if category == "valuation":
                gitems = [it for it in gitems
                          if it.get("metric_name") not in _VALUATION_CHART_EXCLUDE]
            chart_section = _build_group_bar_chart(gname, gitems, category)
            if chart_section is not None:
                sub_sections.append(chart_section)

        sub_tabs.append({
            "name": cat_label,
            "sections": sub_sections,
        })

    # Fallback when the registry can't be loaded — show whatever is in
    # ratios_payload as a single flat ratio_grid.
    if not sub_tabs:
        items = []
        for k, v in sorted(ratios_payload.items()):
            if k in ("date", "error"):
                continue
            fmt_spec = "pct" if k in _RATIO_PCT_KEYS else "num"
            label = _METRIC_LABELS.get(k, k)
            items.append({"label": label, "value": _fmt(v, fmt_spec)})
        if items:
            sub_tabs.append({
                "name": "Indicadores",
                "sections": [{
                    "title": f"Indicadores (as of {today})",
                    "type": "ratio_grid",
                    "categories": [{"label": "Indicadores", "items": items}],
                }],
            })

    if not sub_tabs:
        return {"type": "text", "text": "Nenhum indicador disponível."}

    return {
        "title": f"Indicadores (as of {today})",
        "type": "subtabs",
        "tabs": sub_tabs,
    }


def _build_growth_ratio_grid_section(ratios_payload: dict, today: str) -> dict | None:
    """[v1.25] Build a ratio_grid section showing ALL growth metrics.

    Moved here from the Indicadores tab (where the "Crescimento" subtab
    was removed in v1.25). Shows:

      - Crescimento 3M / 1A / 5A (simple growth) for Receita, Lucro
        Líquido, Resultado Bruto
      - CAGR 3A / 5A (compound annual) for the same three metrics
      - Taxa de Retenção + Crescimento Sustentável (in "Outros Crescimento")

    Grouped via ``_group_metrics_by_prefix`` into per-metric boxes
    (Receita / Lucro Líquido / Resultado Bruto / Outros Crescimento)
    with horizon-sorted items inside each box.

    Returns ``None`` when no growth metrics are registered (registry
    unavailable or empty).
    """
    items, _ = _build_category_items("growth", ratios_payload)
    if not items:
        return None
    grouped = _group_metrics_by_prefix(items, category_label="Crescimento")
    return {
        "title": f"Crescimento — Indicadores (as of {today})",
        "description": (
            "Crescimento 3M/1A/5A (simples) + CAGR 3A/5A (composto) + "
            "Taxa de Retenção e Crescimento Sustentável. Passe o mouse "
            "sobre cada indicador para ver a fórmula (ⓘ)."
        ),
        "type": "ratio_grid",
        "categories": grouped,
    }
