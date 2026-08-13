"""skills/cvm/financials/report/periods.py -- Period series (TTM / YoY / Anual / Trimestral).

Builds the chart + table sections for the period-series tabs (TTM rolling,
YoY quarterly groups, Anual, Trimestral). Each pair of builders takes
period dicts from the corresponding mode (``ttm()`` / ``yoy_quarterly()`` /
``annual()`` / ``quarterly()``).

Public builders:
  - ``build_ttm_chart(ttm_periods)`` / ``build_ttm_table(ttm_periods)``
  - ``build_yoy_chart(groups)``      / ``build_yoy_table(groups)``
  - ``build_period_table(periods, label)`` / ``build_period_chart(periods, label)``
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none


# ── TTM chart builder (v1.15) ────────────────────────────────────────────────

def build_ttm_chart(ttm_periods: list[dict]) -> dict | None:
    """Build a line chart showing TTM Revenue + EBITDA + Net Income over time.

    Args:
        ttm_periods: list of TTM period dicts (from ttm() mode) with
                     "quarter" and "metrics" keys.

    Returns None if no valid data.
    """
    labels = []
    revenue = []
    ebitda = []
    net_income = []
    for p in ttm_periods:
        m = p.get("metrics") or {}
        rev = m.get("receita_liquida")
        ebd = m.get("ebitda")
        ni = m.get("lucro_liquido")
        if rev is None and ebd is None and ni is None:
            continue
        labels.append(p.get("quarter", ""))
        revenue.append(_num_or_none(rev))
        ebitda.append(_num_or_none(ebd))
        net_income.append(_num_or_none(ni))

    if not labels:
        return None

    return {
        "type": "chart",
        "title": "Série Temporal Anualizada (TTM)",
        "description": (
            "Receita, EBITDA e Lucro Líquido trailing-12-months (TTM) "
            "recomputados a cada trimestre. Dessaonaliza os dados "
            "trimestrais e mostra a tendência real."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita (TTM)", "data": revenue,
                     "borderColor": "#0d9488", "fill": False, "tension": 0.3},
                    {"label": "EBITDA (TTM)", "data": ebitda,
                     "borderColor": "#f59e0b", "fill": False, "tension": 0.3},
                    {"label": "Lucro Líq. (TTM)", "data": net_income,
                     "borderColor": "#3b82f6", "fill": False, "tension": 0.3},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                  "title": {"display": True, "text": "R$ (TTM)"}}},
                "plugins": {
                    "title": {"display": True, "text": "Série Temporal TTM (Anualizada)"},
                },
            },
        },
    }


def build_ttm_table(ttm_periods: list[dict]) -> dict:
    """Build a table showing TTM metrics per period.

    Columns: Período, Receita, EBITDA, Lucro Líquido, Marg. EBITDA, Marg. Líq.
    """
    columns = ["Período", "Receita (TTM)", "EBITDA", "Lucro Líq.",
               "Marg. EBITDA", "Marg. Líq."]
    rows = []
    for p in ttm_periods:
        m = p.get("metrics") or {}
        r = p.get("ratios") or {}
        rows.append([
            p.get("quarter", ""),
            _fmt(m.get("receita_liquida"), "brl"),
            _fmt(m.get("ebitda"), "brl"),
            _fmt(m.get("lucro_liquido"), "brl"),
            _fmt(r.get("marg_ebitda"), "pct"),
            _fmt(r.get("marg_liquida"), "pct"),
        ])
    return {
        "title": "Rolling TTM (Anualizado)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "note": "Trailing 12 months recomputed at each quarter boundary. Deseasonalized.",
    }


# ── YoY Quarterly chart builder (v1.15) ──────────────────────────────────────

def build_yoy_chart(groups: list[dict]) -> dict | None:
    """Build a bar chart showing Revenue YoY growth per quarter group.

    One dataset per quarter (Q1, Q2, Q3, Q4), x-axis = years.
    Shows whether each quarter is growing or shrinking YoY.

    Args:
        groups: list of group dicts (from yoy_quarterly() mode) with
                "quarter" and "periods" keys.

    Returns None if no valid data.
    """
    datasets = []
    all_years: set[int] = set()

    for g in groups:
        q_label = g.get("quarter", "")
        periods = g.get("periods") or []
        if not periods:
            continue

        # [new commit] F16 fix: build year→growth dict so datasets align
        # with the global labels list. Was appending growths sequentially,
        # which misaligned when groups had different year coverage (e.g.,
        # Q1 has 4 years, Q2 has 3 — Q2's data plotted at wrong labels).
        year_to_growth: dict[int, float | None] = {}
        for p in periods:
            year = p.get("year")
            yoy = p.get("yoy_growth") or {}
            growth = yoy.get("receita_liquida")
            if year is not None:
                all_years.add(year)
                year_to_growth[year] = (
                    _num_or_none(growth) * 100 if growth is not None else None
                )

        if year_to_growth:
            datasets.append({
                "label": q_label,
                "data": year_to_growth,  # dict — will be aligned below
            })

    if not datasets:
        return None

    labels = sorted(str(y) for y in all_years)

    # [new commit] Align each dataset with the global labels list.
    # Convert year→growth dicts to ordered lists matching `labels`.
    for ds in datasets:
        year_to_growth = ds.pop("data")
        ds["data"] = [
            year_to_growth.get(int(yr)) for yr in labels
        ]

    return {
        "type": "chart",
        "title": "Crescimento YoY por Trimestre",
        "description": (
            "Crescimento YoY (year-over-year) da Receita Líquida por "
            "trimestre (Q1/Q2/Q3/Q4) ao longo dos anos. Mostra se cada "
            "trimestre está crescendo ou encolhendo em relação ao mesmo "
            "trimestre do ano anterior."
        ),
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "Crescimento YoY (%)"}}},
                "plugins": {
                    "title": {"display": True, "text": "Crescimento YoY da Receita por Trimestre"},
                },
            },
        },
    }


def build_yoy_table(groups: list[dict]) -> list[dict]:
    """Build per-quarter tables showing YoY comparison across years.

    [new commit] MAJOR REWRITE — now groups by QUARTER (was by year).
    User feedback: "its grouped by year, should be by quarter, to see the
    differences of 4t26 and 4t25 and so on". Each quarter (Q1/Q2/Q3/Q4)
    gets its own table showing all available years for that quarter,
    newest year first. This lets you compare 4T2026 vs 4T2025 vs 4T2024
    directly.

    Returns a list of section dicts (one per quarter), in Q4→Q1 order.
    """
    columns = ["Ano", "Receita", "EBITDA", "Lucro Líq.", "Receita YoY %"]

    # Flatten all periods across groups, collect by quarter number.
    by_quarter: dict[int, list[dict]] = {}
    quarter_labels: dict[int, str] = {}
    for g in groups:
        q_label = g.get("quarter", "")
        for p in g.get("periods") or []:
            year = p.get("year")
            qnum = p.get("quarter", 0)
            if year is None:
                continue
            by_quarter.setdefault(qnum, []).append({
                "year": year,
                "quarter": q_label,
                "receita": (p.get("metrics") or {}).get("receita_liquida"),
                "ebitda": (p.get("metrics") or {}).get("ebitda"),
                "lucro": (p.get("metrics") or {}).get("lucro_liquido"),
                "yoy": (p.get("yoy_growth") or {}).get("receita_liquida"),
            })
            quarter_labels[qnum] = q_label

    sections: list[dict] = []
    # Q4 first (most relevant for full-year comparison), then Q3, Q2, Q1
    for qnum in sorted(by_quarter.keys(), reverse=True):
        periods = sorted(by_quarter[qnum], key=lambda x: x["year"], reverse=True)
        rows = []
        for p in periods:
            rows.append([
                str(p["year"]),
                _fmt(p["receita"], "brl"),
                _fmt(p["ebitda"], "brl"),
                _fmt(p["lucro"], "brl"),
                _fmt(p["yoy"], "pct"),
            ])
        q_label = quarter_labels.get(qnum, f"Q{qnum}")
        sections.append({
            "title": f"{q_label} — YoY por Ano",
            "description": (
                f"Comparação year-over-year do {q_label}. "
                "YoY % = (atual - ano anterior) / |ano anterior|. "
                "Mostra a evolução deste trimestre específico ao longo dos anos."
            ),
            "type": "table",
            "columns": columns,
            "rows": rows,
        })

    if not sections:
        return [{
            "title": "Comparação YoY por Trimestre",
            "type": "text",
            "text": "Sem dados trimestrais disponíveis.",
        }]

    return sections


# ── Period table builder (v1.16) ────────────────────────────────────────────

def build_period_table(periods: list[dict], label: str) -> dict:
    """Build a table showing key metrics across multiple periods.

    Used by the Anual and Trimestral tabs to show raw period data.
    Columns: Período, Receita, EBIT, EBITDA, Lucro Líq., Marg. EBITDA, Marg. Líq.
    """
    columns = ["Período", "Receita", "EBIT", "EBITDA", "Lucro Líq.",
               "Marg. EBITDA", "Marg. Líq."]
    rows = []
    for p in periods:
        m = p.get("metrics") or {}
        r = p.get("ratios") or {}
        rows.append([
            p.get("period", "—"),
            _fmt(m.get("receita_liquida"), "brl"),
            _fmt(m.get("ebit"), "brl"),
            _fmt(m.get("ebitda"), "brl"),
            _fmt(m.get("lucro_liquido"), "brl"),
            _fmt(r.get("marg_ebitda"), "pct"),
            _fmt(r.get("marg_liquida"), "pct"),
        ])
    return {
        "title": f"{label} — {len(rows)} períodos",
        "type": "table",
        "columns": columns,
        "rows": rows,
    }


# ── New chart builders (v1.16) ────────────────────────────────────────────────

def build_period_chart(periods: list[dict], label: str) -> dict | None:
    """Build a multi-line chart for the Anual or Trimestral tabs.

    [v1.16] New chart showing Receita/EBITDA/Lucro Líq. across periods.
    Used by both the Anual and Trimestral tabs (raw period data).
    """
    # Filter out periods without data, sort oldest-first.
    sorted_periods = sorted(
        [p for p in periods if p.get("period")],
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

    chart_type = "line" if label.lower().startswith("anual") else "bar"
    return {
        "type": "chart",
        "title": f"Trajetória — {label}",
        "description": (
            f"Receita Líquida, EBITDA e Lucro Líquido por período ({label}). "
            "Mostra a evolução temporal dos principais indicadores."
        ),
        "chart_data": {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [
                    {"label": "Receita Líquida", "data": revenue,
                     "backgroundColor": "#0d9488", "borderColor": "#0d9488"},
                    {"label": "EBITDA", "data": ebitda,
                     "backgroundColor": "#f59e0b", "borderColor": "#f59e0b"},
                    {"label": "Lucro Líquido", "data": net_income,
                     "backgroundColor": "#3b82f6", "borderColor": "#3b82f6"},
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {"y": {"ticks": {},
                                 "title": {"display": True, "text": "R$"}}},
                "plugins": {
                    "title": {"display": True,
                              "text": f"Receita, EBITDA e Lucro — {label}"},
                },
            },
        },
    }
