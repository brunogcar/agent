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
    """Build 6 KPI cards with pre-formatted values + QoQ deltas.

    [v2.4] Added QoQ % deltas (green for positive, red for negative) by
    comparing the latest TTM period vs the previous TTM period.
    """
    # Extract TTM metrics if available, fall back to annual.
    # [v3] TTM periods are OLDEST-FIRST — use [-1] (newest) and [-2] (prev).
    ttm_metrics: dict = {}
    ttm_prev_metrics: dict = {}
    if ttm_result and isinstance(ttm_result, dict) and ttm_result.get("status") == "ok":
        ttm_periods = ttm_result.get("periods") or []
        if ttm_periods:
            ttm_metrics = ttm_periods[-1].get("metrics") or {}
            if len(ttm_periods) > 1:
                ttm_prev_metrics = ttm_periods[-2].get("metrics") or {}

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

    # [v2.4] Compute QoQ deltas for the 3 financial KPIs.
    def _qoq_delta(current, previous):
        """Compute QoQ % delta. Returns formatted string or None."""
        if current is None or previous is None or previous == 0:
            return None
        pct = (current - previous) / abs(previous)
        return _fmt(pct, "pct")

    receita_delta = _qoq_delta(receita_val, ttm_prev_metrics.get("receita_liquida"))
    ebitda_delta = _qoq_delta(ebitda_val, ttm_prev_metrics.get("ebitda"))
    lucro_delta = _qoq_delta(lucro_val, ttm_prev_metrics.get("lucro_liquido"))

    return [
        {
            "label": "Receita (TTM)",
            "value": _fmt(receita_val, "brl"),
            "unit": "BRL",
            "delta": receita_delta,
        },
        {
            "label": "EBITDA (TTM)",
            "value": _fmt(ebitda_val, "brl"),
            "unit": "BRL",
            "delta": ebitda_delta,
        },
        {
            "label": "Lucro Líquido (TTM)",
            "value": _fmt(lucro_val, "brl"),
            "unit": "BRL",
            "delta": lucro_delta,
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

    # [v4] Latest-annual headline — TWO two_column blocks side-by-side.
    # Block 1: Resultado (absolute R$) | Margens (% values).
    # Block 2: Balanço | Fluxo de Caixa.
    # Margins split OUT of Resultado into their own "Margens" table per user
    # request. positive_green=True so positive % render green; negative_red
    # so negative R$ (e.g. FCI) render red.
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        r = latest_annual_period.get("ratios") or {}

        # Block 1 left: Resultado (absolute R$ only — no margins)
        resultado_rows = [
            {"label": "Período", "value": latest_annual_period.get("period", "—")},
            {"label": "Receita Líquida", "value": _fmt(m.get("receita_liquida"),   "brl")},
            {"label": "Lucro Bruto", "value": _fmt(m.get("lucro_bruto"),       "brl")},
            {"label": "EBIT", "value": _fmt(m.get("ebit"),              "brl")},
            {"label": "EBITDA", "value": _fmt(m.get("ebitda"),            "brl")},
            {"label": "Lucro Líquido", "value": _fmt(m.get("lucro_liquido"),     "brl")},
        ]

        # Block 1 right: Margens (3 % values, split out of Resultado)
        margens_rows = [
            {"label": "Margem Bruta", "value": _fmt(r.get("marg_bruta"),    "pct")},
            {"label": "Margem EBITDA", "value": _fmt(r.get("marg_ebitda"),   "pct")},
            {"label": "Margem Líquida", "value": _fmt(r.get("marg_liquida"),  "pct")},
        ]

        sections.append({
            "type": "two_column",
            "left_title": "Latest Annual — Resultado",
            "left_rows": resultado_rows,
            "right_title": "Latest Annual — Margens",
            "right_rows": margens_rows,
            "negative_red": True,
            "positive_green": True,
        })

        # Block 2 left: Balanço
        balanco_rows = [
            {"label": "Ativo Total", "value": _fmt(m.get("ativo_total"),       "brl")},
            {"label": "Patrimônio Liq.", "value": _fmt(m.get("patrimonio_liquido"),"brl")},
            {"label": "Caixa", "value": _fmt(m.get("caixa"),             "brl")},
            {"label": "Dívida Bruta", "value": _fmt(m.get("divida_bruta"),      "brl")},
        ]

        # Block 2 right: Fluxo de Caixa
        fluxo_rows = [
            {"label": "FCO", "value": _fmt(m.get("fco"), "brl")},
            {"label": "FCI", "value": _fmt(m.get("fci"), "brl")},
        ]

        sections.append({
            "type": "two_column",
            "left_title": "Latest Annual — Balanço",
            "left_rows": balanco_rows,
            "right_title": "Latest Annual — Fluxo de Caixa",
            "right_rows": fluxo_rows,
            "negative_red": True,
            "positive_green": True,
        })

    # [v4] Quarterly trend — sortable, default newest-first, with
    # chronological data-value on period cells so re-sorting by "Período"
    # toggles true chronological asc/desc (not lexicographic on "QtYYYY").
    # Period dict carries year + quarter (meses); we derive a
    # "YYYY-QQ" sort key.
    if quarterly_periods:
        # [v24] Quarterly Trend with % evolution columns (QoQ delta)
        # [v2.5 fix] The delta is relative to the PREVIOUS trimester (the
        # OLDER period in time), NOT the newer one. The old logic iterated
        # newest-first with `prev_metrics = m` set at the END of the loop,
        # so `prev_metrics` was actually the NEWER period — the deltas were
        # inverted AND shifted by one row (the newest showed "—" and the
        # oldest showed a delta). Fix: explicitly sort newest-first using
        # a chronological key (robust to either input order), then for row
        # at index i, the "previous in time" is at index i+1 (older). The
        # oldest row (last) has no older period → "—". The newest row
        # (first) shows the delta vs the 2nd newest (correct QoQ).
        def _chron_key(p):
            year = p.get("year")
            quarter = p.get("quarter")
            if year is not None and quarter is not None:
                return (int(year), int(quarter))
            period_label = p.get("period", "")
            try:
                q_str, y_str = period_label.split("T")
                return (int(y_str), int(q_str))
            except (ValueError, AttributeError):
                return (0, 0)
        # Sort oldest-first, then reverse for newest-first display.
        sorted_oldest_first = sorted(quarterly_periods, key=_chron_key)
        newest_first = list(reversed(sorted_oldest_first))
        n = len(newest_first)
        trend_rows = []
        for i, p in enumerate(newest_first):
            m = p.get("metrics") or {}
            period_label = p.get("period", "—")
            # Build chronological sort key: "2T2026" -> "2026-02"
            year = p.get("year")
            quarter = p.get("quarter")
            if year is not None and quarter is not None:
                sort_key = f"{int(year):04d}-{int(quarter):02d}"
            else:
                try:
                    q_str, y_str = period_label.split("T")
                    sort_key = f"{int(y_str):04d}-{int(q_str):02d}"
                except (ValueError, AttributeError):
                    sort_key = str(period_label)
            # Compute QoQ % for each metric.
            # The "previous in time" is the OLDER period — at index i+1
            # (since we iterate newest-first). Oldest row has no older → "—".
            def _qoq(curr_val, prev_val):
                if curr_val is None or prev_val is None or prev_val == 0:
                    return "—"
                pct = (curr_val - prev_val) / abs(prev_val)
                return _fmt(pct, "pct")
            rev = m.get("receita_liquida")
            ebd = m.get("ebitda")
            liq = m.get("lucro_liquido")
            if i + 1 < n:
                prev_m = newest_first[i + 1].get("metrics") or {}
                rev_pct = _qoq(rev, prev_m.get("receita_liquida"))
                ebd_pct = _qoq(ebd, prev_m.get("ebitda"))
                liq_pct = _qoq(liq, prev_m.get("lucro_liquido"))
            else:
                rev_pct = "—"
                ebd_pct = "—"
                liq_pct = "—"
            trend_rows.append([
                {"text": period_label, "data-value": sort_key},
                _fmt(rev, "brl"), rev_pct,
                _fmt(ebd, "brl"), ebd_pct,
                _fmt(liq, "brl"), liq_pct,
            ])
        sections.append({
            "title": "Quarterly Trend",
            "type": "table",
            "negative_red": True,
            "positive_green": True,
            "columns": ["Período", "Receita", "Δ%", "EBITDA", "Δ%", "Lucro Liq.", "Δ%"],
            "rows": trend_rows,
            "sortable": True,
            "default_sort": {"column": 0, "direction": "desc"},
            "sort_types": ["text", "text", "text", "text", "text", "text", "text"],
            "column_align": ["left", "right", "right", "right", "right", "right", "right"],
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
    """Build a chart showing Receita/EBITDA/Lucro Líq. bars + price line over annual periods.

    [v1.16] New chart for the Overview tab — gives users an immediate
    visual sense of the company's revenue + earnings trajectory without
    having to navigate to the DRE or Anual tabs.

    [v1.23 F2] Now accepts an optional ``company`` parameter; when provided,
    a 4th dataset (year-end closing price) is added on a secondary right
    Y-axis so users can compare fundamentals with share-price trajectory.

    [v2.4] Revamped to match the unified v2.3 chart style: line → bar,
    unified colors (Receita=orange, EBITDA=magenta, Lucro=purple via
    ``_CHART_COLORS``), values in R$ (mi) with ``_absMillions`` +
    ``_fixedYWidth=90`` for vertical alignment with the other tabs.
    The price overlay is kept (meaningful for annual trajectory) but
    re-styled: GREEN line (#0d9488 — the old Receita teal color, now free
    since Receita moved to orange) on the right Y-axis, drawn on top of
    the bars so it reads as a reference line over the fundamentals.
    """
    from skills.cvm.financials.report._helpers import _CHART_COLORS

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

    # [v2.4] Bar chart with unified color scheme (orange/magenta/purple).
    # Values divided by 1e6 → R$ (mi) y-axis. _absMillions + _fixedYWidth
    # for alignment with the other tabs' trend charts.
    def _to_millions(v):
        return v / 1_000_000 if v is not None else None

    datasets = [
        {"label": "Receita Líquida", "data": [_to_millions(v) for v in revenue],
         "backgroundColor": _CHART_COLORS["receita"],
         "borderColor": _CHART_COLORS["receita"],
         "yAxisID": "y", "order": 3},
        {"label": "EBITDA", "data": [_to_millions(v) for v in ebitda],
         "backgroundColor": _CHART_COLORS["ebitda"],
         "borderColor": _CHART_COLORS["ebitda"],
         "yAxisID": "y", "order": 3},
        {"label": "Lucro Líquido", "data": [_to_millions(v) for v in net_income],
         "backgroundColor": _CHART_COLORS["lucro"],
         "borderColor": _CHART_COLORS["lucro"],
         "yAxisID": "y", "order": 3},
    ]

    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$ (mi)"}},
    }

    # [v2.4] Price overlay — GREEN line (#0d9488) on the right Y-axis,
    # drawn ON TOP of the bars (order: 0 so Chart.js renders it last).
    # This color was Receita's old teal; it's now free since Receita
    # moved to orange in the unified scheme. User request: "keep price
    # as line as reference, as green over all the other bars".
    if company:
        price_series_data = _fetch_year_end_prices(company, labels)
        if any(v is not None for v in price_series_data):
            datasets.append({
                "label": "Preço (R$)",
                "data": price_series_data,
                "type": "line",
                "borderColor": "#0d9488",
                "backgroundColor": "#0d9488",
                "borderDash": [5, 5],
                "fill": False,
                "tension": 0.3,
                "yAxisID": "y1",
                "pointRadius": 3,
                "order": 0,  # draw on top of bars
            })
            scales["y1"] = {
                "type": "linear", "position": "right",
                "grid": {"drawOnChartArea": False},
                "ticks": {},
                "title": {"display": True, "text": "Preço (R$)"},
            }

    return {
        "type": "chart",
        "title": "Trajetória de Receita, EBITDA e Lucro (Anual)",
        "description": (
            "Receita Líquida, EBITDA e Lucro Líquido anuais em R$ (mi). "
            "Barras mostram a magnitude de cada componente do resultado."
            + (" Linha verde tracejada = preço de fechamento em 31/Dez (eixo direito)."
               if company and "y1" in scales else "")
        ),
        "chart_data": {
            "type": "bar",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "_fixedYWidth": 90,
                "_absMillions": True,
                "scales": scales,
                "plugins": {
                    "title": {"display": True, "text": "Receita, EBITDA e Lucro Líquido"},
                },
            },
        },
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

    _HEATMAP_TOOLTIPS = {
        "ROE": "ROE = Lucro Líquido / Patrimônio Líquido. >20% bom, <10% ruim.",
        "ROA": "ROA = Lucro Líquido / Ativo Total. >10% bom, <5% ruim.",
        "ROIC": "ROIC = NOPAT / Capital Investido. >12% bom, <7% ruim.",
        "Margem Líquida": "Margem Líquida = Lucro / Receita. >15% bom, <5% ruim.",
        "Margem EBITDA": "Margem EBITDA = EBITDA / Receita. >25% bom, <10% ruim.",
        "Margem Operacional": "Margem Oper. = EBIT / Receita. >15% bom, <5% ruim.",
        "D/E": "Dívida/PL. <0,5 bom, >2,0 ruim.",
        "Dív. Líq./EBITDA": "Dív. Líq./EBITDA. <1,5 bom, >3,5 ruim.",
        "Liquidez Corrente": "Ativo Circ. / Passivo Circ. >1,5 bom, <1,0 ruim.",
        "Cresc. Receita 1Y": "Crescimento Receita YoY. >10% bom, <0% ruim.",
    }

    def _heat(val, good, bad, reverse=False, tooltip=""):
        if val is None:
            return {"text": "—", "bg": "", "color": "", "tooltip": tooltip}
        if reverse:
            if val <= good:
                return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
            elif val <= bad:
                return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
            else:
                return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}
        else:
            if val >= good:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
            elif val >= bad:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
            else:
                return {"text": f"{val*100:.1f}%", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}

    def _heat_ratio(val, good_min, bad_min, tooltip=""):
        if val is None:
            return {"text": "—", "bg": "", "color": "", "tooltip": tooltip}
        if val >= good_min:
            return {"text": f"{val:.2f}", "bg": "rgba(34,197,94,0.2)", "color": "#16a34a", "tooltip": tooltip}
        elif val >= bad_min:
            return {"text": f"{val:.2f}", "bg": "rgba(245,158,11,0.2)", "color": "#d97706", "tooltip": tooltip}
        else:
            return {"text": f"{val:.2f}", "bg": "rgba(220,38,38,0.2)", "color": "#dc2626", "tooltip": tooltip}

    rows = [
        ["ROE", _heat(ratios.get("roe"), 0.20, 0.10, tooltip=_HEATMAP_TOOLTIPS["ROE"])],
        ["ROA", _heat(ratios.get("roa"), 0.10, 0.05, tooltip=_HEATMAP_TOOLTIPS["ROA"])],
        ["ROIC", _heat(ratios.get("roic"), 0.12, 0.07, tooltip=_HEATMAP_TOOLTIPS["ROIC"])],
        ["Margem Líquida", _heat(ratios.get("net_margin"), 0.15, 0.05, tooltip=_HEATMAP_TOOLTIPS["Margem Líquida"])],
        ["Margem EBITDA", _heat(ratios.get("ebitda_margin"), 0.25, 0.10, tooltip=_HEATMAP_TOOLTIPS["Margem EBITDA"])],
        ["Margem Operacional", _heat(ratios.get("operating_margin"), 0.15, 0.05, tooltip=_HEATMAP_TOOLTIPS["Margem Operacional"])],
        ["D/E", _heat(ratios.get("debt_equity"), 0.5, 2.0, reverse=True, tooltip=_HEATMAP_TOOLTIPS["D/E"])],
        ["Dív. Líq./EBITDA", _heat(ratios.get("net_debt_ebitda"), 1.5, 3.5, reverse=True, tooltip=_HEATMAP_TOOLTIPS["Dív. Líq./EBITDA"])],
        ["Liquidez Corrente", _heat_ratio(ratios.get("current_ratio"), 1.5, 1.0, tooltip=_HEATMAP_TOOLTIPS["Liquidez Corrente"])],
        ["Cresc. Receita 1Y", _heat(ratios.get("revenue_growth_1y"), 0.10, 0.0, tooltip=_HEATMAP_TOOLTIPS["Cresc. Receita 1Y"])],
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


# ── [v2.4] F16 — Quality of Earnings ──────────────────────────────────────────

def build_quality_of_earnings_section(
    annual_periods: list[dict],
    ratios_payload: dict | None = None,
) -> dict | None:
    """[v2.4] F16 — Quality of Earnings section for the Análise de Risco subtab.

    Compares Net Income (Lucro Líquido) vs Operating Cash Flow (FCO) over
    the last 5 annual periods. When NI grows but OCF flatlines or declines
    (or OCF persists below NI), it indicates low earnings quality
    (aggressive accruals, unrealized receivables).

    Returns two sections (returned as a list by the caller's wire-up):
      1. A table with columns [Ano, Lucro Líquido, FCO, Diferença,
         Accruals Ratio, Qualidade] — the accruals ratio is
         ``(NI − OCF) / |NI|``; flagged red when > 0.30 (low quality).
      2. A bar+line chart: FCO bars + Lucro Líquido line overlay (same
         pattern as the DFC FCO-vs-LL chart, but standalone + with the
         accruals ratio flagged).

    Args:
        annual_periods: list of annual period dicts (each with 'period' +
            'metrics' containing 'lucro_liquido' + 'fco'). Newest-first or
            oldest-first — sorted internally to oldest-first for the chart.
        ratios_payload: unused for now (kept for API symmetry with the
            other Análise de Risco builders); reserved for future
            accruals-specific ratios.

    Returns:
        A ``type: "table"`` section dict, or None when fewer than 2 periods
        have both NI + FCO. The caller (dashboard.py) appends this section
        to the Análise de Risco subtab; a second chart section is returned
        as a separate dict via ``build_quality_of_earnings_chart`` when the
        table builds successfully.
    """
    if not annual_periods:
        return None

    # Sort oldest-first for chronological display.
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    # Last 5 periods (or all if fewer).
    last5 = sorted_periods[-5:]

    rows: list[list] = []
    has_data = False
    for p in last5:
        m = p.get("metrics") or {}
        ni = _num_or_none(m.get("lucro_liquido"))
        ocf = _num_or_none(m.get("fco"))
        if ni is None or ocf is None:
            rows.append([
                p.get("period", "—"),
                _fmt(ni, "brl"),
                _fmt(ocf, "brl"),
                "—", "—", "—",
            ])
            continue
        has_data = True
        diff = ni - ocf
        # Accruals ratio = (NI - OCF) / |NI|. > 0.30 → low quality.
        accruals = diff / abs(ni) if ni != 0 else None
        if accruals is None:
            quality = "—"
        elif accruals > 0.30:
            quality = {"text": "⚠ Baixa", "color": "#dc2626"}
        elif accruals > 0.10:
            quality = {"text": "△ Média", "color": "#d97706"}
        else:
            quality = {"text": "✓ Alta", "color": "#16a34a"}
        rows.append([
            p.get("period", "—"),
            _fmt(ni, "brl"),
            _fmt(ocf, "brl"),
            _fmt(diff, "brl"),
            _fmt(accruals, "pct") if accruals is not None else "—",
            quality,
        ])

    if not has_data:
        return None

    # Count consecutive years with accruals > 0.30 for the red-flag note.
    consecutive_low = 0
    max_consecutive = 0
    for r in rows:
        q = r[5]
        if isinstance(q, dict) and "Baixa" in q.get("text", ""):
            consecutive_low += 1
            max_consecutive = max(max_consecutive, consecutive_low)
        else:
            consecutive_low = 0

    note = None
    if max_consecutive >= 2:
        note = (
            f"⚠ Red flag: accruals ratio > 30% por {max_consecutive} anos "
            "consecutivos — lucro não está se convertendo em caixa."
        )

    # [v2.5 fix B33] Add caveat about |NI| denominator fragility.
    caveat = (
        "Nota: o ratio usa |Lucro Líquido| no denominador — instável "
        "quando o lucro é próximo de zero. Para empresas em prejuízo, "
        "interpretar o label com cautela."
    )
    full_note = " | ".join(filter(None, [note, caveat]))

    return {
        "type": "table",
        "title": "Qualidade do Lucro — NI vs FCO (5 anos)",
        "description": (
            "Accruals Ratio = (Lucro Líquido − FCO) / |Lucro Líquido|. "
            "Quando > 30%, o lucro contábil não está se convertendo em "
            "caixa operacional — sinal de qualidade baixa (accruals "
            "agressivos, recebíveis não realizados)."
        ),
        "columns": ["Ano", "Lucro Líquido", "FCO", "Diferença", "Accruals", "Qualidade"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
        "column_align": ["left", "right", "right", "right", "right", "center"],
        "note": full_note,
    }


def build_quality_of_earnings_chart(
    annual_periods: list[dict],
) -> dict | None:
    """[v2.4] F16 — NI vs FCO bar+line chart companion to the QoE table.

    FCO as bars (cyan, matching the DFC FCO-vs-LL chart), Lucro Líquido
    as a line overlay (purple, matching the unified _CHART_COLORS lucro).
    Visualizes the divergence between accounting earnings and operating
    cash flow over the last 5 annual periods.

    Returns a ``type: "chart"`` section dict, or None when fewer than 2
    periods have data.
    """
    from skills.cvm.financials.report._helpers import _CHART_COLORS

    if not annual_periods:
        return None

    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    last5 = sorted_periods[-5:]
    if len(last5) < 2:
        return None

    labels = [str(p.get("period")) for p in last5]
    ni_vals, ocf_vals = [], []
    for p in last5:
        m = p.get("metrics") or {}
        ni = _num_or_none(m.get("lucro_liquido"))
        ocf = _num_or_none(m.get("fco"))
        ni_vals.append(ni / 1_000_000 if ni is not None else None)
        ocf_vals.append(ocf / 1_000_000 if ocf is not None else None)

    if not any(v is not None for v in ni_vals + ocf_vals):
        return None

    # FCO bars (cyan — same as DFC _DFC_COLORS["fco"]) + Lucro Líquido
    # line overlay (purple — unified _CHART_COLORS["lucro"]).
    datasets = [
        {"label": "FCO", "data": ocf_vals,
         "backgroundColor": "#0891b2", "borderColor": "#0891b2",
         "yAxisID": "y", "order": 2},
        {"label": "Lucro Líquido", "data": ni_vals,
         "type": "line",
         "borderColor": _CHART_COLORS["lucro"],
         "backgroundColor": _CHART_COLORS["lucro"],
         "fill": False, "tension": 0.3,
         "yAxisID": "y", "order": 0,
         "pointRadius": 4},
    ]

    return {
        "type": "chart",
        "title": "Qualidade do Lucro — FCO vs Lucro Líquido (5 anos)",
        "description": (
            "Barras cyan = FCO (Fluxo de Caixa Operacional). Linha roxa = "
            "Lucro Líquido. Quando o Lucro cresce mas o FCO não acompanha, "
            "a qualidade dos lucros está caindo (accruals)."
        ),
        "chart_data": {
            "type": "bar",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_fixedYWidth": 90, "_absMillions": True,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$ (mi)"}},
                },
                "plugins": {
                    "title": {"display": True, "text": "FCO vs Lucro Líquido"},
                },
            },
        },
    }
