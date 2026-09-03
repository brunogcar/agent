"""skills/cvm/financials/report/dre.py -- DRE tab builders.

Builds the DRE tab (multi-period comparison table + trend chart + margins
chart + absolute-values bar chart, all inside a period_toggle).

Public builders:
  - ``build_dre_sections(...)`` — top-level sections for the DRE tab.
  - ``build_statement_trend_chart(periods, company, label)`` — generic
    Receita/EBITDA/Lucro Líquido trend chart with optional price overlay.
    Also used by other tabs (DFC/DVA via separate per-statement variants).

Private helpers:
  - ``_build_dre_margins_chart(periods)`` — gross/EBIT/EBITDA/net margins
    line chart.
  - ``_build_dre_abs_chart(periods, period_label)`` — Receita/EBITDA/Lucro
    Líquido absolute-values bar chart (period_label = "Anual" or "Trimestral").
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import (
    _fmt, _num_or_none, _pct_of, _period_sort_key, _CHART_COLORS,
)
from skills.cvm.financials.report.overview import _attach_price_overlay
from skills.cvm.financials.report.statements import _build_period_toggle_sections
from skills.cvm.financials.report.error import _metrics_from_period


# ── Tab 5: DRE (table + margin trend chart) ──────────────────────────────────

def build_dre_sections(
    dre_result: dict,
    annual_periods: list[dict],
    latest_annual_period: dict | None,
    company: str | None = None,
    dre_result_q: dict | None = None,
    quarterly_periods: list[dict] | None = None,
) -> list[dict]:
    """Build the DRE tab: multi-period comparison table + 5Y margin trend chart.

    [v2.2] TTM toggle reverted — TTM data lives only in the standalone
    "Anualizado" tab now. The ``ttm_periods`` param was removed; the
    period_toggle emits only annual + quarterly panels (2-button mode).

    [v1.25 v4] ALL time-series charts are now INSIDE the period_toggle:
      - Trajetória de Receita e Lucro (trend)
      - Evolução das Margens (gross/EBIT/EBITDA/net line chart)
      - Receita, EBITDA e Lucro Líquido (absolute-values bar chart)
    Each has an annual version (built from ``annual_periods``) and a
    quarterly version (built from ``quarterly_periods`` when available).
    Removed the separate ``sections.append()`` calls for the margins and
    absolute-values charts — they're now part of the toggle's annual_chart
    / quarterly_chart lists.

    [v1.24] Quarterly support:
      - Accepts optional ``dre_result_q`` (quarterly DRE statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available) so the
        price-overlay line chart shows finer-grained movement.

    [v1.23 F4] Appends a statement-level trend chart (Receita/EBITDA/
    Lucro Líq. + price overlay on right axis) at the END of the sections.
    Backward-compatible: ``company`` is optional; when None the overlay is
    skipped.
    """
    sections: list[dict] = []

    dre_periods = (dre_result or {}).get("periods") or []
    dre_periods_q = (dre_result_q or {}).get("periods") or []
    q_periods = quarterly_periods or []

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dre_annual_trend = build_statement_trend_chart(dre_periods, company, "DRE")
    dre_quarterly_trend = build_statement_trend_chart(dre_periods_q, company, "DRE") if dre_periods_q else None

    # [v1.25 v4] Build annual + quarterly margins charts.
    dre_annual_margins = _build_dre_margins_chart(annual_periods)
    dre_quarterly_margins = _build_dre_margins_chart(q_periods) if q_periods else None

    # [v11] Removed the _build_dre_abs_chart double chart — the trend chart
    # now shows the same data (Receita/EBITDA/Lucro) as bars, so the separate
    # abs chart was redundant. User: "no need to have the double chart".

    # [v1.25 v4] Collect all annual charts + all quarterly charts (order:
    # trend first, then margins — matches the previous top-level ordering).
    annual_charts = [c for c in
                     [dre_annual_trend, dre_annual_margins]
                     if c is not None]
    quarterly_charts = [c for c in
                        [dre_quarterly_trend, dre_quarterly_margins]
                        if c is not None]

    # [v1.24] Multi-period table (annual + quarterly via period_toggle) +
    # ALL time-series charts INSIDE toggle.
    # [v2.2] TTM toggle reverted — no ttm_periods/ttm_chart kwargs.
    sections.extend(_build_period_toggle_sections(
        "DRE", dre_periods, dre_periods_q, "DRE",
        annual_chart=annual_charts,
        quarterly_chart=quarterly_charts,
    ))

    # Fallback: latest_annual_period metrics table (DRE codes).
    if not sections and latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}
        rows = [
            ["Receita Líquida",       _fmt(m.get("receita_liquida"),     "brl")],
            ["Lucro Bruto",           _fmt(m.get("lucro_bruto"),         "brl")],
            ["EBIT",                  _fmt(m.get("ebit"),                "brl")],
            ["D&A",                   _fmt(m.get("da"),                  "brl")],
            ["EBITDA",                _fmt(m.get("ebitda"),              "brl")],
            ["EBITDA Method",         str(m.get("ebitda_method") or "—")],
            ["Resultado Financeiro",  _fmt(m.get("resultado_financeiro"),"brl")],
            ["Lucro Líquido",         _fmt(m.get("lucro_liquido"),       "brl")],
            ["", ""],
            ["Margem Bruta",          _fmt(r.get("marg_bruta"),          "pct")],
            ["Margem EBIT",           _fmt(r.get("marg_ebit"),           "pct")],
            ["Margem EBITDA",         _fmt(r.get("marg_ebitda"),         "pct")],
            ["Margem Líquida",        _fmt(r.get("marg_liquida"),        "pct")],
        ]
        sections.append({
            "title": "DRE (Latest Annual)",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })

    if not sections:
        sections.append({
            "type": "text",
            "text": "DRE data unavailable for this company.",
        })

    # [v1.25 v4] Margins chart + absolute-values chart + trend chart are now
    # ALL INSIDE the period_toggle (above). No separate sections.append calls.

    return sections


def _build_dre_margins_chart(periods: list[dict]) -> dict | None:
    """[v11] Build the DRE margins evolution bar chart (was line chart).

    Changed from line to bar per user request: "Evolução das Margens with
    bars and new color scheme". Colors now use the unified _CHART_COLORS
    scheme (dark maroon / light pink / pale pink / maroon) instead of the
    old green/blue/amber/purple lines.

    Works for BOTH annual + quarterly periods (each period must have a
    ``ratios`` dict with ``marg_*`` keys).

    Returns None if fewer than 2 periods or all margin values are None.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    gross, operating, net, ebitda = [], [], [], []
    for p in sorted_periods:
        r = p.get("ratios") or {}
        gross.append(_pct_of(r.get("marg_bruta")))
        operating.append(_pct_of(r.get("marg_ebit")))
        net.append(_pct_of(r.get("marg_liquida")))
        ebitda.append(_pct_of(r.get("marg_ebitda")))
    if not any(v is not None for v in gross + operating + net + ebitda):
        return None
    return {
        "type": "chart",
        "title": "Evolução das Margens",
        "description": (
            "Margens Bruta, Líquida, EBIT e EBITDA ao longo do tempo. "
            "Mostra a trajetória da rentabilidade operacional."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Marg. Bruta",  "data": gross,
                     "backgroundColor": _CHART_COLORS["marg_bruta"],
                     "borderColor": _CHART_COLORS["marg_bruta"]},
                    {"label": "Marg. Líquida","data": net,
                     "backgroundColor": _CHART_COLORS["marg_liquida"],
                     "borderColor": _CHART_COLORS["marg_liquida"]},
                    {"label": "Marg. EBIT",   "data": operating,
                     "backgroundColor": _CHART_COLORS["marg_ebit"],
                     "borderColor": _CHART_COLORS["marg_ebit"]},
                    {"label": "Marg. EBITDA", "data": ebitda,
                     "backgroundColor": _CHART_COLORS["marg_ebitda"],
                     "borderColor": _CHART_COLORS["marg_ebitda"]},
                ],
            },
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_fixedYWidth": 90,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "Margem (%)"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Margens Operacionais ao Longo do Tempo"},
                },
            },
        },
    }


def _build_dre_abs_chart(periods: list[dict], period_label: str) -> dict | None:
    """[v1.25 v4] Build the Receita/EBITDA/Lucro Líquido absolute-value bar
    chart from a list of period dicts. Works for BOTH annual + quarterly
    periods (each period must have a ``metrics`` dict with ``receita_liquida``
    / ``ebitda`` / ``lucro_liquido`` keys).

    Args:
        periods: list of period dicts (annual or quarterly).
        period_label: "Anual" or "Trimestral" — used in the chart title.

    Returns None if fewer than 2 periods or all values are None.
    Used by ``build_dre_sections`` to build annual + quarterly versions for
    the period_toggle.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    revenue_abs, ebitda_abs, ni_abs = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        revenue_abs.append(_num_or_none(m.get("receita_liquida")))
        ebitda_abs.append(_num_or_none(m.get("ebitda")))
        ni_abs.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in revenue_abs + ebitda_abs + ni_abs):
        return None
    return {
        "type": "chart",
        "title": f"Receita, EBITDA e Lucro Líquido ({period_label}, R$)",
        "description": (
            f"Valores absolutos {period_label.lower()} de Receita Líquida, "
            "EBITDA e Lucro Líquido. Barras agrupadas por período permitem "
            "comparar a magnitude de cada componente do resultado ao longo "
            "do tempo."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita Líquida", "data": revenue_abs,
                     "backgroundColor": "#0d9488"},
                    {"label": "EBITDA", "data": ebitda_abs,
                     "backgroundColor": "#f59e0b"},
                    {"label": "Lucro Líquido", "data": ni_abs,
                     "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Receita, EBITDA e Lucro por Período"},
                },
            },
        },
    }


def build_statement_trend_chart(
    periods: list[dict], company: str | None, label: str,
) -> dict | None:
    """[v11] Receita/EBITDA/Lucro Líq. bar chart (was line chart).

    Changed from line to bar per user request: "to replace chart Trajetória
    de Receita e Lucro — DRE and add ebitda, with color magenta with bars
    instead of lines as it is". Colors now use the unified _CHART_COLORS
    scheme (orange/magenta/purple) instead of the old teal/amber/blue.

    Used by the DRE tab (income-statement metrics). Same concept as the
    Overview trend chart, but accepts a custom ``label`` so the same builder
    can be reused by future tabs.

    Args:
        periods: annual OR quarterly period dicts.
        company: B3 ticker for the price overlay; None skips the overlay.
        label: chart title suffix (e.g. "DRE").
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    revenue, ebitda, net_income = [], [], []
    for p in sorted_periods:
        m = _metrics_from_period(p)
        revenue.append(_num_or_none(m.get("receita_liquida")))
        ebitda.append(_num_or_none(m.get("ebitda")))
        net_income.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in revenue + ebitda + net_income):
        return None

    # [v11] Bar chart with unified color scheme (orange/magenta/purple)
    # [v15] Add _fixedYWidth + _absMillions for chart alignment with Balanço
    # charts. Values divided by 1e6 → R$ mi y-axis.
    datasets = [
        {"label": "Receita Líquida", "data": [v / 1_000_000 if v is not None else None for v in revenue],
         "backgroundColor": _CHART_COLORS["receita"],
         "borderColor": _CHART_COLORS["receita"]},
        {"label": "EBITDA", "data": [v / 1_000_000 if v is not None else None for v in ebitda],
         "backgroundColor": _CHART_COLORS["ebitda"],
         "borderColor": _CHART_COLORS["ebitda"]},
        {"label": "Lucro Líquido", "data": [v / 1_000_000 if v is not None else None for v in net_income],
         "backgroundColor": _CHART_COLORS["lucro"],
         "borderColor": _CHART_COLORS["lucro"]},
    ]
    # [v11] Removed price overlay — user wants a clean bar chart without
    # the dual-axis price line. Keep _attach_price_overlay available for
    # other callers but don't call it here.
    description = (
        f"Receita Líquida, EBITDA e Lucro Líquido ({label}). "
        "Barras mostram a magnitude de cada componente do resultado."
    )
    return {
        "type": "chart",
        "title": f"Trajetória de Receita, EBITDA e Lucro — {label}",
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_fixedYWidth": 90,
                "_absMillions": True,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$ (mi)"}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": f"Receita, EBITDA e Lucro — {label}"},
                },
            },
        },
    }
