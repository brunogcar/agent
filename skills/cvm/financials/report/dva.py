"""skills/cvm/financials/report/dva.py -- DVA tab builders.

Builds the DVA tab (multi-period comparison table + doughnut chart for
wealth distribution + bar chart for wealth-generation waterfall + trend
chart, with the trend chart inside a period_toggle) plus the dividend
sustainability section.

Public builders:
  - ``build_dva_sections(...)`` — top-level sections for the DVA tab.
  - ``build_dva_trend_chart(periods, company)`` — VA Bruta / VA Líquida /
    Total a Distribuir trend chart with optional price overlay.
  - ``build_dividend_sustainability_section(...)`` — payout + dividend
    coverage table + 5Y dividend trend chart (appended to the DVA tab
    outside the period_toggle).

Private helpers:
  - ``_build_dva_generation_chart(accounts, latest_period)`` — DVA
    generation-side waterfall bar chart (Receitas → Insumos → VA Bruto →
    Retenções → VA Líquido → VA Recebido → Total a Distribuir).
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none, _period_sort_key
from skills.cvm.financials.report.overview import _attach_price_overlay
from skills.cvm.financials.report.statements import _build_period_toggle_sections
from skills.cvm.financials.report.error import _safe_engine_call


# ── Tab 7: DVA (table + doughnut chart) ──────────────────────────────────────

def build_dva_sections(
    dva_result: dict,
    company: str | None = None,
    dva_result_q: dict | None = None,
) -> list[dict]:
    """Build the DVA tab: generation + distribution table + doughnut chart.

    [v2.2] TTM toggle reverted — TTM data lives only in the standalone
    "Anualizado" tab now. The ``ttm_periods`` param was removed; the
    period_toggle emits only annual + quarterly panels (2-button mode).

    [v1.24] Quarterly support:
      - Accepts optional ``dva_result_q`` (quarterly DVA statement result).
      - The multi-period table is wrapped in a ``period_toggle`` section so
        the user can switch between annual + quarterly views.
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table.
      - Trend chart now prefers quarterly periods (when available).

    [v1.23 F4] Appends a DVA trend chart (VA Bruta/VA Líquida/Total a
    Distribuir + price overlay on right axis) at the END of the sections.
    Backward-compatible: ``company`` is optional; when None the overlay is
    skipped.
    """
    sections: list[dict] = []

    dva_periods = (dva_result or {}).get("periods") or []
    dva_periods_q = (dva_result_q or {}).get("periods") or []
    if not dva_periods:
        sections.append({
            "type": "text",
            "text": "DVA data unavailable for this company.",
        })
        return sections

    latest = dva_periods[0]
    accounts = latest.get("accounts") or {}
    if not accounts:
        sections.append({
            "type": "text",
            "text": "DVA accounts not found for the latest period.",
        })
        return sections

    # [v1.25 v3] Build annual + quarterly trend charts, pass into period_toggle.
    dva_annual_trend = build_dva_trend_chart(dva_periods, company)
    dva_quarterly_trend = build_dva_trend_chart(dva_periods_q, company) if dva_periods_q else None

    # [v1.24] Multi-period table + charts INSIDE period_toggle.
    # [v2.2] TTM toggle reverted — no ttm_periods/ttm_chart kwargs.
    sections.extend(_build_period_toggle_sections(
        "DVA", dva_periods, dva_periods_q, "DVA",
        annual_chart=dva_annual_trend,
        quarterly_chart=dva_quarterly_trend,
    ))

    # If neither annual nor quarterly table could be built, fall back to a
    # bare text notice so the tab isn't empty.
    if not sections:
        sections.append({
            "type": "text",
            "text": "DVA multi-period comparison unavailable.",
        })

    # Doughnut chart: wealth distribution.
    # [v1.16 DVA-fix] Two fixes vs the v1.15 builder:
    #
    # 1. NEW TAXONOMY: CVM DVA codes changed in 2012+. The OLD taxonomy
    #    used 8.01 (Pessoal), 8.02 (Governo), 8.03 (Credores), 8.04
    #    (Acionistas). The NEW taxonomy uses 7.08.01 (Pessoal), 7.08.02
    #    (Governo), 7.08.03 (Credores), 7.08.04 (Acionistas — Remuneração
    #    de Capitais Próprios). Most filers post-2012 use the NEW codes;
    #    the old builder only matched "8.0X" prefixes, so all 7.08.*
    #    accounts fell into "Outros". We now match BOTH taxonomies.
    #
    # 2. DOUBLE-COUNT: The old builder summed parent + children codes
    #    (e.g., 7.08.04 + 7.08.04.01 + 7.08.04.02), inflating the
    #    "Acionistas" slice. The new builder uses depth-3 codes ONLY
    #    (7.08.01 / 7.08.02 / 7.08.03 / 7.08.04) for the new taxonomy
    #    and depth-2 codes (8.01 / 8.02 / 8.03 / 8.04) for the old
    #    taxonomy. Deeper codes (7.08.04.01 JCP, 7.08.04.02 Dividendos)
    #    are skipped because they are sub-components of the parent.
    # [v1.16.1 DVA-fix] Two bugs fixed from v1.16:
    #
    # 1. SAME-DEPTH SIBLING DROP: when a filer reports only children
    #    (e.g., 7.08.04.01 JCP + 7.08.04.02 Dividendos) without a parent
    #    (7.08.04 roll-up), the v1.16 dedup kept only the FIRST child
    #    because depth(4) < depth(4) is False. Now: if no depth-3 parent
    #    exists for a prefix, SUM all same-depth children instead of
    #    keeping only one.
    #
    # 2. CROSS-TAXONOMY DOUBLE-COUNT: if a filer reports BOTH new (7.08.04)
    #    AND old (8.04) taxonomies for the same label in the same period,
    #    v1.16 summed both → double-count. Now: prefer the NEW taxonomy
    #    (7.08.*) when both are present; only fall back to old (8.*) when
    #    new is absent for that label.
    distribution_labels = {
        # NEW taxonomy (post-2012) — depth-3 codes under 7.08.*
        "7.08.01": "Pessoal",
        "7.08.02": "Governo",
        "7.08.03": "Credores",
        "7.08.04": "Acionistas",
        "7.08.05": "Outros",
        # OLD taxonomy (pre-2012) — depth-2 codes under 8.*
        "8.01": "Pessoal",
        "8.02": "Governo",
        "8.03": "Credores",
        "8.04": "Acionistas",
    }

    NEW_TAXONOMY_PREFIXES = {"7.08.01", "7.08.02", "7.08.03", "7.08.04", "7.08.05"}

    def _dva_depth(codigo: str) -> int:
        """Number of dot-separated levels in a CVM account code.
        '7.08.04' → 3, '7.08.04.01' → 4, '8.01' → 2."""
        return len(codigo.split("."))

    # Pass 1: collect all distribution-side codes + their depth + matched prefix.
    # dist_rows: (codigo, label, valor, depth, matched_prefix)
    dist_rows: list[tuple[str, str, float, int, str]] = []
    for codigo, acc in accounts.items():
        if (acc.get("section") != "Distribuição"
                or acc.get("valor_brl") is None):
            continue
        label = None
        matched_prefix = None
        for prefix, lbl in distribution_labels.items():
            if codigo == prefix or codigo.startswith(prefix + "."):
                label = lbl
                matched_prefix = prefix
                break
        if label is None:
            continue
        try:
            val = float(acc["valor_brl"])
        except (TypeError, ValueError):
            continue
        dist_rows.append((codigo, label, val, _dva_depth(codigo), matched_prefix))

    # Pass 2: for each prefix, collect ALL values grouped by depth.
    # If a shallow depth exists (parent), use ONLY that (skip children).
    # If no shallow depth exists (only children), SUM all children.
    # best_per_prefix: prefix -> {depth: sum_of_values_at_that_depth}
    per_prefix_by_depth: dict[str, dict[int, float]] = {}
    for codigo, label, val, depth, prefix in dist_rows:
        if prefix not in per_prefix_by_depth:
            per_prefix_by_depth[prefix] = {}
        per_prefix_by_depth[prefix][depth] = per_prefix_by_depth[prefix].get(depth, 0.0) + val

    # For each prefix, pick the shallowest depth's sum.
    best_per_prefix: dict[str, float] = {}
    for prefix, depth_map in per_prefix_by_depth.items():
        shallowest_depth = min(depth_map.keys())
        best_per_prefix[prefix] = depth_map[shallowest_depth]

    # Pass 3: aggregate by label, but prefer NEW taxonomy when both
    # new + old are present for the same label.
    # Group prefixes by label, track which prefixes have new-taxonomy data.
    label_to_prefixes: dict[str, list[str]] = {}
    for prefix, label in distribution_labels.items():
        if prefix in best_per_prefix:
            label_to_prefixes.setdefault(label, []).append(prefix)

    agg: dict[str, float] = {}
    for label, prefixes in label_to_prefixes.items():
        has_new = any(p in NEW_TAXONOMY_PREFIXES for p in prefixes)
        if has_new:
            # Prefer new taxonomy — sum only new-taxonomy prefixes for this label.
            for p in prefixes:
                if p in NEW_TAXONOMY_PREFIXES:
                    agg[label] = agg.get(label, 0.0) + best_per_prefix[p]
        else:
            # Only old taxonomy present — use it.
            for p in prefixes:
                agg[label] = agg.get(label, 0.0) + best_per_prefix[p]

    dist_data = [(label, val) for label, val in agg.items()]

    if dist_data:
        labels = [lbl for lbl, _ in dist_data]
        values = [val for _, val in dist_data]
        # Use absolute values for the chart (DVA distribution is positive).
        abs_values = [abs(v) for v in values]
        sections.append({
            "type": "chart",
            "title": "Distribuição de Riqueza",
            "description": (
                "Distribuição do valor adicionado por stakeholder: Pessoal, "
                "Governo, Credores e Acionistas. Códigos CVM 7.08.01-05 "
                "(nova taxonomia) ou 8.01-04 (antiga)."
            ),
            "chart_data": {
                "type": "doughnut",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "Distribuição de Riqueza",
                        "data": abs_values,
                        "backgroundColor": [
                            "#22c55e",  # Pessoal
                            "#ef4444",  # Governo
                            "#f59e0b",  # Credores
                            "#3b82f6",  # Acionistas
                            "#a855f7",  # Outros
                        ],
                    }],
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    # [v1.13 review-fix] Flag consumed by dashboard.html's
                    # chart-rendering script to attach a tooltip callback
                    # showing each slice's percentage of the total.  The
                    # callback is a JS function (not JSON-serializable), so
                    # we set a flag here and the template injects the
                    # callback at render time.
                    "_tooltipPercent": True,
                },
            },
        })

    # [new commit] NEW chart: DVA generation-side decomposition (bar chart).
    # User feedback: "DVA generation-side bar chart showing the wealth
    # creation waterfall: 7.01 Receitas, 7.03 Insumos, 7.04 VA Bruto,
    # 7.05 Retenções, 7.06 VA Líquido, 7.07 VA Recebido, 7.08 Total a
    # Distribuir". Codes are already in `accounts` (DVA mode fetches them).
    gen_chart = _build_dva_generation_chart(accounts, latest)
    if gen_chart is not None:
        sections.append(gen_chart)

    # [v1.25 v3] Trend chart is now INSIDE the period_toggle (above).

    return sections


def _build_dva_generation_chart(accounts: dict, latest_period: dict) -> dict | None:
    """Build the DVA generation-side waterfall bar chart.

    Shows the wealth-creation pipeline: Receitas → (−Insumos) → VA Bruto →
    (−Retenções) → VA Líquido → (+VA Recebido) → Total a Distribuir.

    Codes per user spec (post-2012 CVM DVA taxonomy):
      7.01 Receitas / 7.03 Insumos / 7.04 VA Bruto / 7.05 Retenções /
      7.06 VA Líquido / 7.07 VA Recebido / 7.08 Total a Distribuir.

    Returns None when fewer than 2 of the codes are present (graceful
    degradation when the filer doesn't report a full DVA).
    """
    # (codigo, label) pairs in waterfall order.
    gen_codes = [
        ("7.01", "Receitas"),
        ("7.03", "Insumos"),
        ("7.04", "VA Bruto"),
        ("7.05", "Retenções"),
        ("7.06", "VA Líquido"),
        ("7.07", "VA Recebido"),
        ("7.08", "Total a Distribuir"),
    ]
    labels: list[str] = []
    values: list[float] = []
    for code, label in gen_codes:
        acc = accounts.get(code) or {}
        v = acc.get("valor_brl")
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        labels.append(f"{code} — {label}")
        values.append(fv)
    if len(labels) < 2:
        return None
    period_label = (latest_period or {}).get("period") \
        or (latest_period or {}).get("data_fim_exerc") or "Latest"
    return {
        "type": "chart",
        "title": f"Geração de Riqueza — {period_label}",
        "description": (
            "Cascata de geração de valor adicionado: Receitas → Insumos → "
            "VA Bruto → Retenções → VA Líquido → VA Recebido → Total a "
            "Distribuir. Códigos CVM 7.01-7.08 (nova taxonomia)."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Geração de Riqueza (R$)",
                    "data": values,
                    "backgroundColor": "#0d9488",
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"ticks": {},
                          "title": {"display": True, "text": "R$"}},
                    "x": {"ticks": {"maxRotation": 45, "minRotation": 30}},
                },
                "plugins": {
                    "title": {"display": True, "text": "DVA — Geração de Valor Adicionado"},
                },
            },
        },
    }


def build_dva_trend_chart(
    periods: list[dict], company: str | None,
) -> dict | None:
    """[v1.23 F4 / v1.24] VA Bruta/VA Líquida/Total a Distribuir trend chart with overlay.

    Used by the DVA tab. Reads DVA account codes:
      - 7.04 → VA Bruto
      - 7.06 → VA Líquido
      - 7.08 → Total a Distribuir

    [v1.24] Sort key upgraded to ``_period_sort_key`` for chronological
    quarterly ordering. Reads from ``accounts`` dict (works for both annual
    + quarterly — both have ``accounts`` post-reshape).

    Args:
        periods: DVA period dicts (each has ``period`` + ``accounts``).
        company: B3 ticker for the price overlay; None skips the overlay.
    """
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
        key=_period_sort_key,
    )
    if len(sorted_periods) < 2:
        return None
    labels = [str(p.get("period")) for p in sorted_periods]
    va_bruta, va_liquida, total_dist = [], [], []
    for p in sorted_periods:
        accounts = p.get("accounts") or {}
        va_bruta.append(_num_or_none((accounts.get("7.04") or {}).get("valor_brl")))
        va_liquida.append(_num_or_none((accounts.get("7.06") or {}).get("valor_brl")))
        total_dist.append(_num_or_none((accounts.get("7.08") or {}).get("valor_brl")))
    if not any(v is not None for v in va_bruta + va_liquida + total_dist):
        return None

    datasets = [
        {"label": "VA Bruta", "data": va_bruta,
         "borderColor": "#0d9488", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "VA Líquida", "data": va_liquida,
         "borderColor": "#f59e0b", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
        {"label": "Total a Distribuir", "data": total_dist,
         "borderColor": "#3b82f6", "fill": False, "tension": 0.3,
         "yAxisID": "y"},
    ]
    scales: dict = {
        "y": {"type": "linear", "position": "left", "ticks": {},
              "title": {"display": True, "text": "R$"}},
    }
    has_overlay = _attach_price_overlay(datasets, scales, company, labels)
    description = (
        "Valor Adicionado Bruto (7.04), Líquido (7.06) e Total a "
        "Distribuir (7.08)."
    )
    if has_overlay:
        description += (
            " Linha roxa tracejada = preço de fechamento de fim de período (eixo direito)."
        )
    return {
        "type": "chart",
        "title": "Trajetória da Geração de Valor",
        "description": description,
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": scales,
                "plugins": {
                    "title": {"display": True,
                              "text": "Geração de Valor Adicionado por Período"},
                },
            },
        },
    }


# ── [new commit] F13: Dividend sustainability ────────────────────────────────

def build_dividend_sustainability_section(
    ratios_payload: dict,
    latest_annual_period: dict | None,
    company: str,
    today: str,
) -> list[dict]:
    """[new commit] F13 — Dividend sustainability (appended to DVA tab).

    Shows:
      - Payout ratio (from ratios_payload, computed as dividends / NI).
      - Dividend Coverage = Lucro Líquido / Dividends Paid.
      - 5Y dividend trend chart (BRL total, from dividends_paid_periods).

    Args:
        ratios_payload: dict from compute_all_ratios. May contain "payout"
            when the dpa metric isn't excluded (currently dashboard.py
            excludes ["lpa", "vpa", "dpa", "rps"] — payout is an alias of
            dpa, so it's also excluded; we fall back to computing payout
            from latest_annual_period["ratios"]["payout"]).
        latest_annual_period: latest annual period dict (or None).
        company: ticker/CNPJ — needed for dividends_paid_at + ttm_earnings_at.
        today: YYYY-MM-DD for TTM anchoring.
    """
    sections: list[dict] = []

    from skills.cvm.calculations.engines.dva.dividends_paid import (
        dividends_paid_at, dividends_paid_periods)
    from skills.cvm.calculations.engines.dre.earnings import ttm_earnings_at

    # Payout: prefer ratios_payload, then latest_annual_period.ratios.payout.
    payout = ratios_payload.get("payout")
    if payout is None and latest_annual_period:
        payout = (latest_annual_period.get("ratios") or {}).get("payout")
    payout = _num_or_none(payout)

    # TTM dividends paid (BRL total) + TTM net income.
    div_ttm = _safe_engine_call(dividends_paid_at, company, today)
    ni_ttm = _safe_engine_call(ttm_earnings_at, company, today)

    # Dividend Coverage = NI / |Dividends Paid|. Dividends are negative
    # outflow in the DVA engine (matches capex convention); take abs.
    div_coverage: float | None = None
    if ni_ttm is not None and div_ttm is not None and div_ttm != 0:
        div_coverage = ni_ttm / abs(div_ttm)

    # [v1.25 v2] Tooltips on metric name (1st column).
    rows = [
        [{"text": "Payout Ratio (LL → Dividendos)", "tooltip": "Payout = Dividendos / Lucro Líquido. % do lucro distribuído aos acionistas."}, _fmt(payout, "pct")],
        [{"text": "Dividendos Pagos (TTM, BRL)", "tooltip": "Dividendos pagos TTM = DVA 7.08.04 (Remuneração de Capital Próprio). Valor negativo (saída)."}, _fmt(div_ttm, "brl")],
        [{"text": "Lucro Líquido (TTM, BRL)", "tooltip": "Lucro Líquido TTM = DRE 3.09 (últimos 12 meses)"}, _fmt(ni_ttm, "brl")],
        [{"text": "Cobertura de Dividendos = LL / Div", "tooltip": "Cobertura = Lucro Líquido / Dividendos. <1.5x = risco de corte. >2x = saudável."}, _fmt(div_coverage, "num")],
    ]
    sections.append({
        "title": "Sustentabilidade de Dividendos",
        "description": (
            "Payout Ratio = Dividendos / Lucro Líquido. Cobertura de "
            "Dividendos = Lucro Líquido / Dividendos — abaixo de 1.5x "
            "indica risco de cortes em cenários de queda de lucro. Acima "
            "de 2x é considerado saudável."
        ),
        "type": "table",
        "columns": ["Indicador", "Valor"],
        "rows": rows,
        "note": (
            "Dividendos Pagos vem do DVA 7.08.04 (Remuneração de Capitais "
            "Próprios) — é o valor agregado reportado pela empresa, não o "
            "por-ação da B3."
        ),
    })

    # 5Y dividend trend chart from dividends_paid_periods.
    div_periods = _safe_engine_call(dividends_paid_periods, company)
    if isinstance(div_periods, list) and len(div_periods) >= 2:
        labels = [str(p.get("date", ""))[:10] for p in div_periods]
        values = []
        for p in div_periods:
            v = p.get("ttm_dividends_paid")
            values.append(_num_or_none(v))
        if any(v is not None for v in values):
            sections.append({
                "type": "chart",
                "title": "Dividendos Pagos — TTM ao longo do tempo",
                "description": (
                    "Série histórica de dividendos pagos (TTM, BRL) — "
                    "agregado reportado no DVA 7.08.04. Mostra a "
                    "trajetória da distribuição de capital aos acionistas."
                ),
                "chart_data": {
                    "type": "line",
                    "data": {
                        "labels": labels,
                        "datasets": [{
                            "label": "Dividendos Pagos (TTM)",
                            "data": values,
                            "borderColor": "#a855f7",
                            "backgroundColor": "#a855f7",
                            "fill": False,
                            "tension": 0.3,
                        }],
                    },
                    "options": {
                        "responsive": True,
                        "maintainAspectRatio": False,
                        "scales": {
                            "y": {"ticks": {},
                                  "title": {"display": True, "text": "R$ (TTM)"}},
                        },
                        "plugins": {
                            "title": {"display": True,
                                      "text": "Evolução dos Dividendos Pagos"},
                        },
                    },
                },
            })

    return sections
