"""skills/cvm/financials/report/overview.py -- Overview tab builders.

Builds:
  - KPI cards row (``build_overview_kpis``)
  - Overview tab sections: summary text + latest-annual headline table +
    quarterly trend table (``build_overview_sections``)
  - Annual trend chart with optional price overlay
    (``build_overview_trend_chart``)
  - Financials radar chart (``build_financials_radar``)
  - Financials heatmap table (``build_financials_heatmap``)
  - Year-end price fetcher + price-overlay helper shared by the per-statement
    trend charts (``_fetch_year_end_prices``, ``_attach_price_overlay``).

The trend chart helpers ``_fetch_year_end_prices`` + ``_attach_price_overlay``
are imported by ``report/dre.py``, ``report/dfc.py``, ``report/dva.py`` for
their per-statement trend charts.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none
from skills.cvm.financials.report.error import annual_metric


# ── KPI cards (top-level) ────────────────────────────────────────────────────

def build_overview_kpis(
    latest_annual_period: dict | None,
    roe_val: float | None,
    roic_val: float | None,
    net_debt_ebitda_val: float | None,
    ttm_result: dict | None = None,
) -> list[dict]:
    """Build 6 KPI cards with pre-formatted values.

    [new commit] F9 fix: "Receita (TTM)" now shows ACTUAL TTM data (from
    ttm_result), not the annual DFP value. Was calling annual_metric() which
    returns the latest annual period — only equals TTM on Dec 31. Now
    prefers ttm_result["periods"][-1]["metrics"] with annual fallback for
    new filers (<4 quarters of ITR history).
    """
    # [new commit] Extract TTM metrics if available, fall back to annual.
    ttm_metrics: dict = {}
    if ttm_result and isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
        ttm_periods = ttm_result.get("periods") or []
        if ttm_periods:
            ttm_metrics = ttm_periods[0].get("metrics") or {}

    # Receita: prefer TTM, fall back to annual
    receita_val = ttm_metrics.get("receita_liquida")
    if receita_val is None:
        receita_val = annual_metric(latest_annual_period, "receita_liquida")
    # EBITDA: prefer TTM, fall back to annual
    ebitda_val = ttm_metrics.get("ebitda")
    if ebitda_val is None:
        ebitda_val = annual_metric(latest_annual_period, "ebitda")
    # Lucro Líquido: prefer TTM, fall back to annual
    lucro_val = ttm_metrics.get("lucro_liquido")
    if lucro_val is None:
        lucro_val = annual_metric(latest_annual_period, "lucro_liquido")

    return [
        {
            "label": "Receita (TTM)",
            "value": _fmt(receita_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "EBITDA (TTM)",
            "value": _fmt(ebitda_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "Lucro Líquido (TTM)",
            "value": _fmt(lucro_val, "brl"),
            "unit": "BRL",
        },
        {
            "label": "ROE",
            "value": _fmt(roe_val, "pct"),
            "unit": "ratio",
        },
        {
            "label": "ROIC",
            "value": _fmt(roic_val, "pct"),
            "unit": "ratio",
        },
        {
            "label": "Dívida Líquida/EBITDA",
            "value": _fmt(net_debt_ebitda_val, "num"),
            "unit": "x",
        },
    ]


# ── Tab 1: Overview ──────────────────────────────────────────────────────────

def build_overview_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
    ratios_payload: dict,
) -> list[dict]:
    """Build Overview tab: latest-annual summary table + quarterly trend +
    optional freshness table. Carries a short summary text at the top.
    """
    sections: list[dict] = []

    summary_lines: list[str] = []
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        summary_lines.append(
            f"Período mais recente: {latest_annual_period.get('period', '—')}."
        )
        summary_lines.append(
            f"Receita Líquida: {_fmt(m.get('receita_liquida'), 'brl')}. "
            f"EBITDA: {_fmt(m.get('ebitda'), 'brl')} "
            f"(método {m.get('ebitda_method', '—')}). "
            f"Lucro Líquido: {_fmt(m.get('lucro_liquido'), 'brl')}."
        )
    else:
        summary_lines.append("Dados anuais indisponíveis para esta empresa.")
    if ratios_payload.get("roe") is not None or ratios_payload.get("roic") is not None:
        summary_lines.append(
            f"ROE: {_fmt(ratios_payload.get('roe'), 'pct')} • "
            f"ROIC: {_fmt(ratios_payload.get('roic'), 'pct')} • "
            f"Dív.Líq/EBITDA: {_fmt(ratios_payload.get('net_debt_ebitda'), 'num')}."
        )
    sections.append({
        "type": "text",
        "text": " ".join(summary_lines),
    })

    # Latest-annual headline metrics table
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}
        # [v1.25] Tooltips now on the FIRST column (metric name/label),
        # not the value cell. User feedback: "tooltips should be on the
        # metric name (e.g. 'Receita Líquida'), not on the value".
        def _label(text: str, tooltip: str) -> dict:
            return {"text": text, "tooltip": tooltip}

        rows = [
            ["Período",           latest_annual_period.get("period", "—")],
            [_label("Receita Líquida",
                    "Receita Líquida = DRE 3.01 (Receita de Vendas)"),
                                  _fmt(m.get("receita_liquida"),   "brl")],
            [_label("Lucro Bruto",
                    "Lucro Bruto = DRE 3.02 (Receita - CPV)"),
                                  _fmt(m.get("lucro_bruto"),       "brl")],
            [_label("EBIT",
                    "EBIT = DRE 3.05 (Resultado antes de juros e impostos)"),
                                  _fmt(m.get("ebit"),              "brl")],
            [_label("EBITDA",
                    "EBITDA = EBIT + D&A (DFC 6.01.01.02)"),
                                  _fmt(m.get("ebitda"),            "brl")],
            [_label("Lucro Líquido",
                    "Lucro Líquido = DRE 3.09 (Resultado do período)"),
                                  _fmt(m.get("lucro_liquido"),     "brl")],
            [_label("Margem Bruta",
                    "Margem Bruta = Lucro Bruto / Receita Líquida"),
                                  _fmt(r.get("marg_bruta"),        "pct")],
            [_label("Margem EBITDA",
                    "Margem EBITDA = EBITDA / Receita Líquida"),
                                  _fmt(r.get("marg_ebitda"),       "pct")],
            [_label("Margem Líquida",
                    "Margem Líquida = Lucro Líquido / Receita Líquida"),
                                  _fmt(r.get("marg_liquida"),      "pct")],
            [_label("Ativo Total",
                    "Ativo Total = BPA 1"),
                                  _fmt(m.get("ativo_total"),       "brl")],
            [_label("Patrimônio Liq.",
                    "PL = BPP 2.03"),
                                  _fmt(m.get("patrimonio_liquido"),"brl")],
            [_label("Caixa",
                    "Caixa = BPA 1.01.01"),
                                  _fmt(m.get("caixa"),             "brl")],
            [_label("Divida Bruta",
                    "Dívida Bruta = BPP 2.01.04 + 2.02.01"),
                                  _fmt(m.get("divida_bruta"),      "brl")],
            [_label("FCO",
                    "Fluxo de Caixa Operacional = DFC 6.01"),
                                  _fmt(m.get("fco"),               "brl")],
            [_label("FCI",
                    "Fluxo de Caixa de Investimento = DFC 6.02"),
                                  _fmt(m.get("fci"),               "brl")],
        ]
        sections.append({
            "title": "Latest Annual Summary",
            "type": "table",
            "columns": ["Indicador", "Valor"],
            "rows": rows,
        })

    # Quarterly trend table (oldest-first reversed for display newest-first)
    if quarterly_periods:
        trend_rows = []
        for p in reversed(quarterly_periods):
            m = p.get("metrics") or {}
            trend_rows.append([
                p.get("period", "—"),
                _fmt(m.get("receita_liquida"), "brl"),
                _fmt(m.get("ebitda"),          "brl"),
                _fmt(m.get("lucro_liquido"),   "brl"),
            ])
        sections.append({
            "title": "Quarterly Trend",
            "type": "table",
            "columns": ["Período", "Receita", "EBITDA", "Lucro Liq."],
            "rows": trend_rows,
        })

    # [v1.16] Freshness tables removed from Overview — the freshness footer
    # at the dashboard level (built by modes/dashboard.py) shows the last
    # sync timestamp + last synced period in a compact single-line format.
    # No need for two bulky tables here.
    return sections


# ── New chart builders (v1.16) ────────────────────────────────────────────────

def _fetch_year_end_prices(company: str, year_labels: list[str]) -> list[float | None]:
    """Fetch Dec-31 (or closest prior trading day) close price for each year label.

    [v1.23 F2] Used by Overview/DFC/DVA trend charts to add a price overlay
    on a secondary right-axis. Returns a list aligned with ``year_labels``
    (None entries when price data is missing or fetch fails).

    Args:
        company: B3 ticker (e.g. "PETR4").
        year_labels: list of year strings (e.g. ["2020", "2021", "2022"]).
    """
    if not company or not year_labels:
        return [None] * len(year_labels)
    try:
        from skills.cvm.calculations.engines.price import price_series
    except Exception:
        return [None] * len(year_labels)
    # Single fetch for the full year range — much cheaper than N round-trips.
    first_year = min(year_labels)
    last_year = max(year_labels)
    date_from = f"{first_year}-01-01"
    date_to = f"{last_year}-12-31"
    try:
        series = price_series(company, date_from, date_to)
    except Exception:
        series = []
    if not series:
        return [None] * len(year_labels)
    # Index by year (YYYY). Prefer the latest available date <= Dec-31 of that
    # year; price_series already filters refdate within [date_from, date_to]
    # and returns oldest-first. Take the last entry of each year.
    by_year: dict[str, float] = {}
    for point in series:
        d = point.get("date") or ""
        if len(d) >= 4:
            by_year[d[:4]] = float(point.get("close"))
    return [by_year.get(y) for y in year_labels]


def build_overview_trend_chart(
    annual_periods: list[dict], company: str | None = None,
) -> dict | None:
    """Build a multi-line chart showing Receita/EBITDA/Lucro Líq. over annual periods.

    [v1.16] New chart for the Overview tab — gives users an immediate
    visual sense of the company's revenue + earnings trajectory without
    having to navigate to the DRE or Anual tabs.

    [v1.23 F2] Now accepts an optional ``company`` parameter; when provided,
    a 4th dataset (year-end closing price) is added on a secondary right
    Y-axis so users can compare fundamentals with share-price trajectory.
    """
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) < 2:
        return None

    labels = [str(p.get("period")) for p in sorted_periods]
    revenue, ebitda, net_income = [], [], []
    for p in sorted_periods:
        m = p.get("metrics") or {}
        revenue.append(_num_or_none(m.get("receita_liquida")))
        ebitda.append(_num_or_none(m.get("ebitda")))
        net_income.append(_num_or_none(m.get("lucro_liquido")))

    if not any(v is not None for v in revenue + ebitda + net_income):
        return None

    datasets = [
        {"label": "Receita Líquida", "data": revenue,
         "borderColor": "#0d9488", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "EBITDA", "data": ebitda,
         "borderColor": "#f59e0b", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "Lucro Líquido", "data": net_income,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]

    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }

    # [v1.23 F2] Price overlay on right Y-axis (purple dashed line).
    if company:
        price_series_data = _fetch_year_end_prices(company, labels)
        if any(v is not None for v in price_series_data):
            datasets.append({
                "label": "Preço (R$)",
                "data": price_series_data,
                "borderColor": "#a855f7",
                "backgroundColor": "#a855f7",
                "borderDash": [5, 5],
                "fill": False,
                "tension": 0.3,
                "yAxisID": "y1",
                "pointRadius": 3,
            })
            scales["y1"] = {
                "type": "linear", "position": "right",
                "grid": {"drawOnChartArea": False},
                "ticks": {},
                "title": {"display": True, "text": "Preço (R$)"},
            }

    return {
        "type": "chart",
        "title": "Trajetória de Receita e Lucro (Anual)",
        "description": (
            "Receita Líquida, EBITDA e Lucro Líquido anuais. Mostra a "
            "trajetória de crescimento e rentabilidade da empresa."
            + (" Linha roxa tracejada = preço de fechamento em 31/Dez (eixo direito)."
               if company and "y1" in scales else "")
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True, "text": "Receita, EBITDA e Lucro Líquido"},
                },
            },
        },
        "price_range_selector": True,
        "price_full_labels": [f"{l}-12-31" for l in labels],
        "price_full_datasets": [
            {"data": revenue},
            {"data": ebitda},
            {"data": net_income},
        ],
        "price_full_data": revenue,
    }


def _attach_price_overlay(
    datasets: list[dict], scales: dict, company: str | None, labels: list[str],
) -> bool:
    """[v1.23 F4] Append a year-end price dataset + right-axis scale.

    Mutates ``datasets`` and ``scales`` in place. Returns True when an
    overlay was added (caller can use this to amend the description).
    """
    if not company or not labels:
        return False
    prices = _fetch_year_end_prices(company, labels)
    if not any(v is not None for v in prices):
        return False
    datasets.append({
        "label": "Preço (R$)",
        "data": prices,
        "borderColor": "#a855f7",
        "backgroundColor": "#a855f7",
        "borderDash": [5, 5],
        "fill": False,
        "tension": 0.3,
        "yAxisID": "y1",
        "pointRadius": 3,
    })
    scales["y1"] = {
        "type": "linear", "position": "right",
        "grid": {"drawOnChartArea": False},
        "ticks": {},
        "title": {"display": True, "text": "Preço (R$)"},
    }
    return True


# ── v1.22: Radar chart + Heatmap (adapted from valuation v2.0) ───────────────

def build_financials_radar(ratios_payload: dict | None) -> dict | None:
    """Build a radar chart comparing key financial dimensions.

    Shows 6 axes: Rentabilidade (ROE), Crescimento (revenue_growth_1y),
    Liquidez (current_ratio), Alavancagem (inverse of D/E), Margem (net_margin),
    Eficiência (asset_turnover). All values normalized to 0-100 scale.

    Returns a chart section dict, or None if fewer than 3 metrics available.
    """
    if not isinstance(ratios_payload, dict):
        return None
    # [v1.22 fix] In financials, ratios_payload is a FLAT dict ({"roe": 0.31, ...}),
    # NOT wrapped in {"ratios": {...}}. Use it directly.
    ratios = ratios_payload

    def _norm_pct(val, max_val=0.5):
        if val is None: return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_ratio(val, max_val=3.0):
        if val is None: return None
        return max(0, min(100, (val / max_val) * 100))

    def _norm_inverse(val, max_val=3.0):
        if val is None: return None
        return max(0, 100 - min(100, (val / max_val) * 100))

    roe_score = _norm_pct(ratios.get("roe"), 0.4)
    growth_score = _norm_pct(ratios.get("revenue_growth_1y"), 0.3)
    liq_score = _norm_ratio(ratios.get("current_ratio"), 3.0)
    lev_score = _norm_inverse(ratios.get("debt_equity"), 3.0)
    margin_score = _norm_pct(ratios.get("net_margin"), 0.3)
    eff_score = _norm_ratio(ratios.get("asset_turnover"), 2.0)

    scores = [roe_score, growth_score, liq_score, lev_score, margin_score, eff_score]
    if sum(1 for s in scores if s is not None) < 3:
        return None

    chart_data = {
        "type": "radar",
        "data": {
            "labels": ["Rentabilidade", "Crescimento", "Liquidez", "Alavancagem", "Margem", "Eficiência"],
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
        "title": "Radar Financeiro — Visão Multidimensional",
        "description": (
            "Score 0-100 por dimensão. Rentabilidade: ROE. Crescimento: receita 1Y. "
            "Liquidez: corrente. Alavancagem: D/E inverso (menor = melhor). "
            "Margem: líquida. Eficiência: giro do ativo."
        ),
        "chart_data": chart_data,
    }


def build_financials_heatmap(ratios_payload: dict | None) -> dict | None:
    """Build a heatmap table of financial metrics with color coding.

    Each metric is color-coded: green (good), yellow (neutral), red (bad).
    Colors are based on standard financial thresholds.

    Returns a heatmap section dict, or None if no data available.
    """
    if not isinstance(ratios_payload, dict):
        return None
    # [v1.22 fix] In financials, ratios_payload is a FLAT dict — use directly.
    ratios = ratios_payload

    def _heat(val, good, bad, reverse=False):
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if reverse:
            if val <= good:
                return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val <= bad:
                return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}
        else:
            if val >= good:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
            elif val >= bad:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
            else:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    def _heat_ratio(val, good_min, bad_min):
        if val is None:
            return {"text": "—", "bg": "", "color": ""}
        if val >= good_min:
            return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a"}
        elif val >= bad_min:
            return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706"}
        else:
            return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626"}

    rows = [
        ["ROE", _heat(ratios.get("roe"), 0.20, 0.10)],
        ["ROA", _heat(ratios.get("roa"), 0.10, 0.05)],
        ["ROIC", _heat(ratios.get("roic"), 0.12, 0.07)],
        ["Margem Líquida", _heat(ratios.get("net_margin"), 0.15, 0.05)],
        ["Margem EBITDA", _heat(ratios.get("ebitda_margin"), 0.25, 0.10)],
        ["Margem Operacional", _heat(ratios.get("operating_margin"), 0.15, 0.05)],
        ["D/E", _heat(ratios.get("debt_equity"), 0.5, 2.0, reverse=True)],
        ["Dív. Líq./EBITDA", _heat(ratios.get("net_debt_ebitda"), 1.5, 3.5, reverse=True)],
        ["Liquidez Corrente", _heat_ratio(ratios.get("current_ratio"), 1.5, 1.0)],
        ["Cresc. Receita 1Y", _heat(ratios.get("revenue_growth_1y"), 0.10, 0.0)],
    ]

    return {
        "type": "heatmap",
        "title": "Heatmap Financeiro — Indicadores Coloridos",
        "description": (
            "Verde = bom, Amarelo = neutro, Vermelho = ruim. "
            "Thresholds baseados em práticas para B3."
        ),
        "columns": ["Métrica", "Valor"],
        "rows": rows,
    }
