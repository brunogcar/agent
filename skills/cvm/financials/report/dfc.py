"""skills/cvm/financials/report/dfc.py -- DFC tab builders.

Builds the DFC tab (multi-period comparison table + trend chart + stacked-bar
chart + FCO-vs-Lucro-Líquido earnings-quality chart, all inside a
period_toggle) plus the standalone DFC quality analysis section.

Public builders:
  - ``build_dfc_sections(...)`` — top-level sections for the DFC tab.
  - ``build_dfc_trend_chart(periods, company)`` — FCO/FCI/FCF trend chart
    with optional price overlay.
  - ``build_dfc_quality_section(...)`` — point-in-time TTM DFC quality table
    (appended OUTSIDE the period_toggle by the dashboard).

Private helpers:
  - ``_build_dfc_stacked_chart(periods)`` — FCO/FCI/FCF stacked bar chart.
  - ``_build_dfc_fco_vs_ll_chart(periods)`` — FCO vs Lucro Líquido line chart
    (earnings-quality divergence).
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none, _period_sort_key
from skills.cvm.financials.report.overview import _attach_price_overlay
from skills.cvm.financials.report.statements import _build_period_toggle_sections
from skills.cvm.financials.report.error import _metrics_from_period, _safe_engine_call


# ── Tab 6: DFC (table + stacked bar chart) ───────────────────────────────────

def build_dfc_sections(
    dfc_result: dict,
    annual_periods: list[dict],
    latest_annual_period: dict | None,
    company: str | None = None,
    dfc_result_q: dict | None = None,
    quarterly_periods: list[dict] | None = None,
    ttm_periods: list[dict] | None = None,
) -> list[dict]:
    """Build the DFC tab: multi-period comparison table + 5Y FCO/FCI/FCF chart.

    [v2.1] TTM (Anualizado) toggle support — same pattern as DRE:
      - Accepts optional ``ttm_periods`` (normalized TTM period dicts).
      - When provided, a 3rd "TTM" toggle panel is added to the period_toggle
        section containing a small TTM metrics table + a TTM trend chart
        (FCO/FCI/FCF built via ``build_dfc_trend_chart``).
      - TTM is a flow statement (rolling 4-quarter sum), so the deseasonalized
        FCO/FCI/FCF movement is more meaningful than quarterly noise.

    [v1.25 v4] ALL time-series charts are now INSIDE the period_toggle:
      - Trajetória de FCO/FCI/FCF (trend)
      - Fluxos de Caixa (stacked bar — FCO/FCI/FCF)
      - FCO vs Lucro Líquido (earnings-quality line chart — moved here from
        ``build_dfc_quality_section`` so it switches with the toggle)
    Each has an annual version (built from ``annual_periods``) and a
    quarterly version (built from ``quarterly_periods`` when available).
    Removed the separate ``sections.append()`` calls for the stacked bar
    chart — it's now part of the toggle's annual_chart / quarterly_chart.

    The "Qualidade do Fluxo de Caixa" TABLE (TTM values) STAYS OUTSIDE the
    toggle — it's a point-in-time table, not a time-series. It continues to
    be produced by ``build_dfc_quality_section`` and appended to
    ``dfc_sections`` by the dashboard.

    [v1.24] Quarterly support:
      - Accepts optional ``dfc_result_q`` (quarterly DFC statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available).

    [v1.23 F4] Appends a DFC trend chart (FCO/FCI/FCF + price overlay on
    right axis) at the END of the sections. Backward-compatible.
    """
    sections: list[dict] = []

    dfc_periods = (dfc_result or {}).get("periods") or []
    dfc_periods_q = (dfc_result_q or {}).get("periods") or []
    q_periods = quarterly_periods or []
    ttm_p = ttm_periods or []

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dfc_annual_trend = build_dfc_trend_chart(dfc_periods, company)
    dfc_quarterly_trend = build_dfc_trend_chart(dfc_periods_q, company) if dfc_periods_q else None

    # [v2.1] Build TTM trend chart (FCO/FCI/FCF TTM).
    dfc_ttm_trend = build_dfc_trend_chart(ttm_p, company) if ttm_p else None

    # [v1.25 v4] Build annual + quarterly stacked-bar charts (FCO/FCI/FCF).
    dfc_annual_stacked = _build_dfc_stacked_chart(annual_periods)
    dfc_quarterly_stacked = _build_dfc_stacked_chart(q_periods) if q_periods else None

    # [v1.25 v4] Build annual + quarterly FCO-vs-Lucro-Líquido line charts
    # (earnings-quality divergence). Moved here from build_dfc_quality_section
    # so the chart switches with the toggle. The quality TABLE (TTM values)
    # stays in build_dfc_quality_section (point-in-time, not time-series).
    dfc_annual_fco_vs_ll = _build_dfc_fco_vs_ll_chart(annual_periods)
    dfc_quarterly_fco_vs_ll = _build_dfc_fco_vs_ll_chart(q_periods) if q_periods else None

    # [v1.25 v4] Collect all annual + quarterly charts (order: trend,
    # stacked bar, FCO vs LL).
    annual_charts = [c for c in
                     [dfc_annual_trend, dfc_annual_stacked, dfc_annual_fco_vs_ll]
                     if c is not None]
    quarterly_charts = [c for c in
                        [dfc_quarterly_trend, dfc_quarterly_stacked, dfc_quarterly_fco_vs_ll]
                        if c is not None]

    # [v1.24] Multi-period table + ALL time-series charts INSIDE period_toggle.
    # [v2.1] Pass ``ttm_periods`` + ``ttm_chart`` so a 3rd TTM panel is added.
    sections.extend(_build_period_toggle_sections(
        "DFC", dfc_periods, dfc_periods_q, "DFC",
        annual_chart=annual_charts,
        quarterly_chart=quarterly_charts,
        ttm_periods=ttm_p,
        ttm_chart=dfc_ttm_trend,
    ))

    if not sections and latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        rows = [
            ["FCO",  _fmt(m.get("fco"), "brl")],
            ["FCI",  _fmt(m.get("fci"), "brl")],
            ["FCF",  _fmt(m.get("fcf"), "brl")],
        ]
        sections.append({
            "title": "DFC (Latest Annual)",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })
    if not sections:
        sections.append({
            "type": "text",
            "text": "DFC data unavailable for this company.",
        })

    # [v1.25 v4] Stacked bar chart + FCO vs LL chart + trend chart are now
    # ALL INSIDE the period_toggle (above). No separate sections.append calls.

    return sections


def _build_dfc_stacked_chart(periods: list[dict]) -> dict | None:
    """[v1.25 v4] Build the DFC stacked-bar chart (FCO/FCI/FCF) from a list
    of period dicts. Works for BOTH annual + quarterly periods (each period
    must have a ``metrics`` dict with ``fco`` / ``fci`` / ``fcf`` keys).

    Returns None if fewer than 2 periods or all values are None.
    Used by ``build_dfc_sections`` to build annual + quarterly versions for
    the period_toggle.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco, fci, fcf = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        fco.append(_num_or_none(m.get("fco")))
        fci.append(_num_or_none(m.get("fci")))
        fcf.append(_num_or_none(m.get("fcf")))
    if not any(v is not None for v in fco + fci + fcf):
        return None
    return {
        "type": "chart",
        "title": "Fluxos de Caixa (empilhado)",
        "description": (
            "Fluxo de Caixa Operacional (FCO), de Investimento (FCI) e de "
            "Financiamento (FCF) ao longo do tempo. Barras empilhadas "
            "mostram a composição total do fluxo de caixa."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "FCO", "data": fco, "backgroundColor": "#22c55e"},
                    {"label": "FCI", "data": fci, "backgroundColor": "#ef4444"},
                    {"label": "FCF", "data": fcf, "backgroundColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True,
                          "title": {"display": True, "text": "R$"}},
                },
                "plugins": {
                    "title": {"display": True, "text": "Fluxos de Caixa Consolidados"},
                },
            },
        },
    }


def _build_dfc_fco_vs_ll_chart(periods: list[dict]) -> dict | None:
    """[v1.25 v4] Build the FCO vs Lucro Líquido line chart (earnings-quality
    divergence) from a list of period dicts. Works for BOTH annual + quarterly
    periods (each period must have a ``metrics`` dict with ``fco`` and
    ``lucro_liquido`` keys).

    Returns None if fewer than 2 periods or all values are None.

    Moved here from ``build_dfc_quality_section`` so the chart switches with
    the period_toggle. The quality TABLE (TTM values) stays in
    ``build_dfc_quality_section`` (point-in-time, not time-series).
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco_series = []
    ni_series = []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        fco_series.append(_num_or_none(m.get("fco")))
        ni_series.append(_num_or_none(m.get("lucro_liquido")))
    if not any(v is not None for v in fco_series + ni_series):
        return None
    return {
        "type": "chart",
        "title": "FCO vs Lucro Líquido",
        "description": (
            "Divergência entre FCO (Fluxo de Caixa Operacional) e Lucro "
            "Líquido ao longo do tempo. Quando o Lucro Líquido cresce mas o "
            "FCO cai (ou fica persistentemente abaixo), pode indicar baixa "
            "qualidade dos lucros (accruals agressivos, recebimentos não "
            "realizados)."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "FCO", "data": fco_series,
                     "borderColor": "#22c55e", "fill": False, "tension": 0.3},
                    {"label": "Lucro Líquido", "data": ni_series,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
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
                              "text": "Divergência FCO vs Lucro Líquido"},
                },
            },
        },
    }


def build_dfc_trend_chart(
    periods: list[dict], company: str | None,
) -> dict | None:
    """[v1.23 F4 / v1.24] FCO/FCI/FCF trend chart with optional price overlay.

    Used by the DFC tab. Plots the 3 DFC sub-totals across periods.

    [v1.24] Now accepts BOTH annual + quarterly periods. Uses
    ``_metrics_from_period`` for quarterly support. Sort key upgraded to
    ``_period_sort_key`` for chronological quarterly ordering.

    Args:
        periods: annual OR quarterly period dicts.
        company: B3 ticker for the price overlay; None skips the overlay.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    fco, fci, fcf = [], [], []
    for p in sorted_periods:
        m = _metrics_from_period(p)
        fco.append(_num_or_none(m.get("fco")))
        fci.append(_num_or_none(m.get("fci")))
        fcf.append(_num_or_none(m.get("fcf")))
    if not any(v is not None for v in fco + fci + fcf):
        return None

    datasets = [
        {"label": "FCO", "data": fco,
         "borderColor": "#22c55e", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "FCI", "data": fci,
         "borderColor": "#ef4444", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "FCF", "data": fcf,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]
    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }
    has_overlay = _attach_price_overlay(datasets, scales, company, labels)
    description = (
        "Fluxos de Caixa Operacional (FCO), de Investimento (FCI) e de "
        "Financiamento (FCF)."
    )
    if has_overlay:
        description += (
            " Linha roxa tracejada = preço de fechamento de fim de período (eixo direito)."
        )
    return {
        "type": "chart",
        "title": "Trajetória dos Fluxos de Caixa",
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True, "text": "FCO, FCI e FCF por Período"},
                },
            },
        },
    }


# ── [new commit] F12: DFC quality analysis ───────────────────────────────────

def build_dfc_quality_section(
    latest_annual_period: dict | None,
    annual_periods: list[dict],
    company: str,
    today: str,
) -> list[dict]:
    """[new commit] F12 — DFC quality analysis (appended to DFC tab).

    Shows:
      - Table: FCO, FCI, FCF (financing), FCF_true = FCO - |CapEx| for the
        latest annual period. NOTE: the financials ``metrics`` dict uses
        "fcf" for FINANCING cash flow (DFC 6.03 — Fluxo de Caixa de
        Financiamento), NOT Free Cash Flow. FCF_true uses a separate key
        to avoid that collision.
      - Cash Conversion Ratio = FCO / Lucro Líquido (TTM).

    [v1.25 v4] The 5Y "FCO vs Lucro Líquido" line chart was MOVED to
    ``build_dfc_sections`` so it lives inside the period_toggle (annual +
    quarterly versions switch with the toggle). This function now returns
    ONLY the quality TABLE (point-in-time TTM values) — not a time-series.
    ``annual_periods`` is kept in the signature for backward compatibility
    with existing callers (e.g. dashboard.py) but is no longer used to
    build a chart here.

    Args:
        latest_annual_period: latest annual period dict (or None).
        annual_periods: list of all annual period dicts (UNUSED since
            v1.25 v4 — kept for backward compat).
        company: ticker/CNPJ — needed for capex_at + ttm_earnings_at calls.
        today: YYYY-MM-DD for the TTM engine anchoring.
    """
    sections: list[dict] = []

    # Engine-backed TTM values (capex + earnings) — best-effort, None on fail.
    from skills.cvm.calculations.engines.dfc.capex import capex_at
    from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
    from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at

    capex_ttm = _safe_engine_call(capex_at, company, today)
    fco_ttm = _safe_engine_call(operating_cf_at, company, today)
    ni_ttm = _safe_engine_call(ttm_earnings_at, company, today)

    # Latest annual FCO/FCI/FCF (financing) — from the metrics dict.
    fco_annual = fci_annual = fcf_financing_annual = None
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        fco_annual = _num_or_none(m.get("fco"))
        fci_annual = _num_or_none(m.get("fci"))
        fcf_financing_annual = _num_or_none(m.get("fcf"))

    # FCF_true = FCO - |CapEx|. Capex from capex_at is negative (outflow),
    # so we take abs then subtract from FCO. Use TTM values when available;
    # fall back to latest annual FCO if TTM engine failed.
    fco_for_fcf = fco_ttm if fco_ttm is not None else fco_annual
    fcf_true: float | None = None
    if fco_for_fcf is not None and capex_ttm is not None:
        fcf_true = fco_for_fcf - abs(capex_ttm)

    # Cash Conversion Ratio = FCO / Lucro Líquido (TTM preferred).
    cash_conversion: float | None = None
    if fco_ttm is not None and ni_ttm is not None and ni_ttm != 0:
        cash_conversion = fco_ttm / ni_ttm
    elif fco_annual is not None:
        # Fall back to latest annual NI.
        if latest_annual_period:
            ni_annual = _num_or_none(
                (latest_annual_period.get("metrics") or {}).get("lucro_liquido"))
            if ni_annual and ni_annual != 0:
                cash_conversion = fco_annual / ni_annual

    # Table: FCO, FCI, FCF (financing), FCF_true, Cash Conversion.
    # [v1.25 v2] Tooltips on metric name (1st column).
    rows = [
        [{"text": "FCO (Anual)", "tooltip": "Fluxo de Caixa Operacional = DFC 6.01 (anual)"}, _fmt(fco_annual, "brl")],
        [{"text": "FCI (Anual)", "tooltip": "Fluxo de Caixa de Investimento = DFC 6.02 (anual)"}, _fmt(fci_annual, "brl")],
        [{"text": "FCF — Financiamento (Anual)", "tooltip": "Fluxo de Caixa de Financiamento = DFC 6.03 (anual). NÃO é Free Cash Flow."}, _fmt(fcf_financing_annual, "brl")],
        [{"text": "FCO (TTM)", "tooltip": "Fluxo de Caixa Operacional TTM (últimos 12 meses)"}, _fmt(fco_ttm, "brl")],
        [{"text": "CapEx (TTM)", "tooltip": "Capital Expenditure TTM = aquisição de imobilizado/intangível (DFC)"}, _fmt(capex_ttm, "brl")],
        [{"text": "FCF Verdadeiro = FCO − |CapEx| (TTM)", "tooltip": "Free Cash Flow = FCO − |CapEx|. Caixa livre após manutenção do negócio."}, _fmt(fcf_true, "brl")],
        [{"text": "Lucro Líquido (TTM)", "tooltip": "Lucro Líquido TTM = DRE 3.09 (últimos 12 meses)"}, _fmt(ni_ttm, "brl")],
        [{"text": "Cash Conversion = FCO / LL", "tooltip": "Cash Conversion Ratio = FCO / Lucro Líquido. >1 = alta qualidade (caixa > lucro)."}, _fmt(cash_conversion, "num")],
    ]
    sections.append({
        "title": "Qualidade do Fluxo de Caixa",
        "description": (
            "FCF Verdadeiro = FCO − |CapEx| (capex é saída de caixa, "
            "por isso subtrai-se o valor absoluto). Cash Conversion Ratio "
            "= FCO / Lucro Líquido — abaixo de 0.8 pode indicar baixa "
            "conversão de lucro em caixa (red flag de qualidade)."
        ),
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
        "note": (
            "Atenção: no Dashboard BR, 'FCF' é o Fluxo de Caixa de "
            "Financiamento (DFC 6.03), NÃO Free Cash Flow. Use a linha "
            "'FCF Verdadeiro' para o Free Cash Flow real."
        ),
    })

    # [v1.25 v4] The 5Y "FCO vs Lucro Líquido" line chart was MOVED to
    # ``build_dfc_sections`` so it lives inside the period_toggle (annual +
    # quarterly versions). The quality TABLE above (TTM values) STAYS here
    # — it's point-in-time, not a time-series. ``annual_periods`` is kept
    # in the signature for backward compatibility with existing callers
    # (e.g. dashboard.py) but is no longer used to build a chart here.

    return sections
