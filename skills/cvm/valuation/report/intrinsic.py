"""report/intrinsic.py — DCF intrinsic-value sensitivity analysis.

Contains:
  - _dcf_at_growth                 — private helper: compute DCF intrinsic
                                      value per share with a CUSTOM FCF growth
                                      rate (mirrors dcf_intrinsic_value_at
                                      but lets caller override Stage-1 growth)
  - build_dcf_sensitivity_section  — DCF in 5 growth scenarios (base ± 2.5%
                                      and ± 5%) + bar chart with current-price
                                      reference line
"""
from __future__ import annotations


# ── V3: DCF Sensitivity Analysis ─────────────────────────────────────────────
#
# Computes DCF intrinsic value at 5 growth-rate scenarios:
#   - growth_rate - 5%   (pessimistic)
#   - growth_rate - 2.5% (conservative)
#   - growth_rate        (base case = revenue_growth_1y)
#   - growth_rate + 2.5% (optimistic)
#   - growth_rate + 5%   (aggressive)
#
# Because dcf_intrinsic_value_at() hardcodes growth=revenue_growth_1y_at(),
# we replicate the DCF formula here using the underlying engine helpers so we
# can sweep the growth rate. Returns: [table_section, chart_section].

def _dcf_at_growth(
    company: str,
    date: str,
    growth_rate: float,
) -> float | None:
    """Compute DCF intrinsic value per share with a CUSTOM growth rate.

    Mirrors ``dcf_intrinsic_value_at()`` from
    ``skills.cvm.calculations.metrics.dcf_intrinsic_value`` but lets the
    caller pass the Stage-1 FCF growth rate instead of pulling it from
    ``revenue_growth_1y_at``.

    Returns None when FCF/WACC/shares are missing or WACC <= terminal growth.
    """
    try:
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
        from skills.cvm.calculations.engines.shares import shares_at
        from skills.cvm.calculations.engines.price import price_at
        from skills.cvm.calculations.metrics.wacc import wacc_at
        from skills.cvm.calculations.growth_helpers import (
            get_terminal_growth, project_fcf, PROJECTION_YEARS,
        )
    except ImportError:
        return None

    fco = operating_cf_at(company, date)
    fci = investing_cf_at(company, date)
    if fco is None or fci is None:
        return None
    base_fcf = fco + fci
    if base_fcf <= 0:
        return None

    wacc = wacc_at(company, date)
    if wacc is None or wacc <= 0:
        return None

    terminal_growth = get_terminal_growth()
    if wacc <= terminal_growth:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    # Stage 1: project FCF at the requested growth rate (project_fcf caps
    # the rate to [-10%, +30%] which is the realistic long-term range).
    fcf_projections = project_fcf(base_fcf, growth_rate, PROJECTION_YEARS)

    pv_stage1 = 0.0
    for t, fcf_t in enumerate(fcf_projections, 1):
        pv_stage1 += fcf_t / (1.0 + wacc) ** t

    # Stage 2: Terminal Value
    fcf_terminal = fcf_projections[-1] * (1.0 + terminal_growth)
    tv = fcf_terminal / (wacc - terminal_growth)
    pv_tv = tv / (1.0 + wacc) ** PROJECTION_YEARS

    intrinsic_value = pv_stage1 + pv_tv
    return intrinsic_value / shares


def build_dcf_sensitivity_section(company: str, date: str) -> list[dict]:
    """Build the DCF sensitivity analysis sections (table + bar chart).

    Computes the DCF intrinsic value per share at 5 growth-rate scenarios
    (base ± 2.5% and ± 5%) so the user can see how sensitive the
    intrinsic-value estimate is to the FCF growth assumption.

    Returns a list of section dicts (table + bar chart). Returns an empty
    list if the base DCF cannot be computed (missing inputs).
    """
    try:
        from skills.cvm.calculations.metrics.revenue_growth import (
            revenue_growth_1y_at,
        )
        from skills.cvm.calculations.engines.price import price_at
    except ImportError:
        return []

    # Base growth rate = revenue_growth_1y, CAPPED at 8% (same cap as DCF metric).
    # [v2.0 fix] Was using uncapped 12.2% growth → R$ 318 absurd DCF.
    # A 1Y revenue spike should NOT be projected 5 years forward.
    # Cap at 8% = Damodaran's upper bound for emerging market large-caps.
    try:
        base_growth = revenue_growth_1y_at(company, date)
    except Exception:
        base_growth = None
    if base_growth is None:
        base_growth = 0.05
    elif base_growth > 0.08:
        base_growth = 0.08
    elif base_growth < -0.05:
        base_growth = -0.05

    scenarios: list[tuple[str, float]] = [
        ("Pessimista",   base_growth - 0.05),
        ("Conservador",  base_growth - 0.025),
        ("Base",         base_growth),
        ("Otimista",     base_growth + 0.025),
        ("Agressivo",    base_growth + 0.05),
    ]

    rows: list[list] = []
    chart_labels: list[str] = []
    chart_values: list[float | None] = []

    current_price = None
    try:
        current_price = price_at(company, date)
    except Exception:
        current_price = None

    for name, g in scenarios:
        try:
            intrinsic = _dcf_at_growth(company, date, g)
        except Exception:
            intrinsic = None
        # Margin of Safety vs current price (None if either side missing)
        mos_pct_str = "—"
        if intrinsic is not None and intrinsic > 0 and current_price is not None and current_price > 0:
            mos = (intrinsic - current_price) / intrinsic
            mos_pct_str = f"{mos * 100:.1f}%"
        rows.append([
            {"text": name, "tooltip": (
                f"Cenário {name}. Taxa de crescimento do FCF = "
                f"{g*100:+.1f}% (base {base_growth*100:.1f}%)."
            )},
            f"{g*100:+.1f}%",
            f"R$ {intrinsic:.2f}" if intrinsic is not None else "—",
            mos_pct_str,
        ])
        chart_labels.append(name)
        chart_values.append(intrinsic)

    # If ALL scenarios returned None (DCF inputs unavailable), return empty.
    if all(v is None for v in chart_values):
        return []

    sections: list[dict] = [{
        "title": "Análise de Sensibilidade — DCF por Cenário",
        "description": (
            "DCF recalculado em 5 cenários de crescimento do FCF "
            "(base ± 2.5% e ± 5%). A base é o revenue_growth_1y real."
        ),
        "type": "table",
        "columns": ["Cenário", "Crescimento", "Valor Intrínseco", "Margem de Segurança"],
        "rows": rows,
        "note": (
            "Premissas mantidas: WACC, terminal growth (IPCA 12M), shares, "
            "FCF base (TTM). Apenas o crescimento do FCF dos 5 anos explícitos varia."
        ),
    }]

    # Bar chart: 5 intrinsic values + horizontal line at current price.
    bar_data = [v if v is not None else 0 for v in chart_values]
    datasets: list[dict] = [{
        "label": "Valor Intrínseco (R$)",
        "data": bar_data,
        "backgroundColor": [
            "#ef4444",  # Pessimista - red
            "#f59e0b",  # Conservador - amber
            "#0d9488",  # Base - teal
            "#3b82f6",  # Otimista - blue
            "#22c55e",  # Agressivo - green
        ],
    }]
    if current_price is not None and current_price > 0:
        datasets.append({
            "label": "Preço Atual",
            "data": [current_price] * len(chart_labels),
            "borderColor": "#6b7280",
            "type": "line",
            "fill": False,
            "tension": 0,
            "pointRadius": 0,
            "borderDash": [6, 4],
        })
    sections.append({
        "type": "chart",
        "title": "Sensibilidade do Valor Intrínseco",
        "description": (
            "Barras: valor intrínseco por cenário. Linha tracejada: preço "
            "atual. Barras acima da linha = cenários em que a ação está "
            "subavaliada."
        ),
        "chart_data": {
            "type": "bar",
            "data": {"labels": chart_labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {"display": True, "text": "R$ / ação"},
                    },
                },
                "plugins": {"legend": {"display": True}},
            },
        },
    })

    return sections
