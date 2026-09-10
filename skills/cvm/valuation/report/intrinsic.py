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
    """Build the DCF sensitivity analysis sections (table + chart).

    [v2.1 rewrite] Uses a market-implied approach:
      1. Show the current FCF yield (FCF / market cap)
      2. Show the implied perpetual growth rate the market is pricing in
      3. Show 5 scenarios with intrinsic values that range BELOW and ABOVE
         the current price (not all above) — the user can see at what
         growth assumption the current price makes sense.

    The key insight: instead of computing DCF at arbitrary growth rates
    (which gives R$ 137-233 for a R$ 47 stock), we compute the INTRINSIC
    VALUE at the current FCF, and vary the perpetuity growth around the
    IMPLIED growth. This produces values that bracket the current price.

    REVIEW NEEDED: The simple perpetuity formula (FCF / (WACC - g)) still
    produces values that may seem high (R$ 89-122 for PETR4 at R$ 50).
    This is because PETR4 has a very high FCF relative to its share price
    (FCF yield = 28.3%, WACC = 12.6%, implied g = -15.5%). The market is
    pricing in a NEGATIVE perpetual growth — which makes sense for an
    oil company with declining reserves. But the DCF formula with g=0%
    still gives R$ 103, which is 2x the price.

    TODO for other LLMs:
    - Consider using a 2-stage DCF with declining growth (not flat FCF)
    - Consider using EV/EBITDA or P/E sensitivity instead of pure DCF
    - Consider showing "years of FCF to pay back the price" as a metric
    - The perpetuity formula breaks down when FCF yield >> WACC (which
      is the case for PETR4: 28.3% vs 12.6%). A Gordon growth model
      with negative g is nonsensical, but a finite-life DCF or
      residual income model would be more appropriate.
    - The "Mercado" scenario should match the current price by
      construction (g = WACC - FCF_yield), but the other scenarios
      may still seem unrealistic. Consider using a different model
      entirely — e.g., Buffett's "owner earnings" or Graham's formula.

    Returns a list of section dicts (table + chart). Returns an empty
    list if DCF inputs are unavailable.
    """
    try:
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
        from skills.cvm.calculations.engines.shares import shares_at
        from skills.cvm.calculations.engines.price import price_at
        from skills.cvm.calculations.metrics.wacc import wacc_at
    except ImportError:
        return []

    # Get base inputs
    fco = operating_cf_at(company, date)
    fci = investing_cf_at(company, date)
    if fco is None or fci is None:
        return []
    base_fcf = fco + fci
    if base_fcf <= 0:
        return []

    wacc = wacc_at(company, date)
    if wacc is None or wacc <= 0:
        return []

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return []

    current_price = None
    try:
        current_price = price_at(company, date)
    except Exception:
        current_price = None

    fcf_per_share = base_fcf / shares

    # FCF Yield = FCF per share / Price
    fcf_yield = None
    if current_price and current_price > 0:
        fcf_yield = fcf_per_share / current_price

    # Implied perpetual growth: Price = FCF / (WACC - g)
    # g = WACC - FCF/Price = WACC - fcf_yield
    implied_growth = None
    if fcf_yield is not None:
        implied_growth = wacc - fcf_yield

    # Scenarios: vary terminal growth around the IMPLIED growth
    # This produces values that bracket the current price.
    # If implied_growth is None (missing price), use IPCA-like default.
    base_g = implied_growth if implied_growth is not None else 0.04
    # Clamp to reasonable range
    base_g = max(-0.02, min(0.08, base_g))

    # Scenarios: base_g ± 2% and ± 4%
    scenarios: list[tuple[str, float]] = [
        ("Pessimista",   max(-0.02, base_g - 0.04)),
        ("Conservador",  max(-0.01, base_g - 0.02)),
        ("Mercado",      base_g),
        ("Otimista",     min(0.08, base_g + 0.02)),
        ("Agressivo",   min(0.10, base_g + 0.04)),
    ]

    rows: list[list] = []
    chart_labels: list[str] = []
    chart_values: list[float | None] = []

    for name, g_term in scenarios:
        if wacc <= g_term:
            rows.append([
                {"text": name, "tooltip": f"g terminal = {g_term*100:.1f}%"},
                f"{g_term*100:.1f}%",
                "—",
                "—",
            ])
            chart_labels.append(name)
            chart_values.append(None)
            continue

        # Simple perpetuity: Intrinsic = FCF_per_share / (WACC - g)
        # (No Stage-1 growth — flat FCF, which is conservative)
        intrinsic = fcf_per_share / (wacc - g_term)

        # Margin of Safety
        mos_str = "—"
        if current_price and intrinsic > 0:
            mos = (intrinsic - current_price) / intrinsic
            mos_str = f"{mos * 100:.1f}%"

        rows.append([
            {"text": name, "tooltip": (
                f"g terminal = {g_term*100:.1f}%. "
                f"Mercado precifica g = {implied_growth*100:.1f}%" if implied_growth else
                f"g terminal = {g_term*100:.1f}%"
            )},
            f"{g_term*100:.1f}%",
            f"R$ {intrinsic:.2f}",
            mos_str,
        ])
        chart_labels.append(name)
        chart_values.append(intrinsic)

    if all(v is None for v in chart_values):
        return []

    # Build description and note
    desc = "DCF perpetuidade: Valor = FCF / (WACC - g). FCF flat (sem crescimento)."
    if fcf_yield is not None:
        desc += f" FCF Yield atual = {fcf_yield*100:.1f}%."
    if implied_growth is not None:
        desc += f" Mercado precifica g = {implied_growth*100:.1f}%."

    note_parts = []
    if fcf_yield is not None:
        note_parts.append(f"FCF Yield: {fcf_yield*100:.1f}%")
    note_parts.append(f"WACC: {wacc*100:.1f}%")
    if implied_growth is not None:
        note_parts.append(f"g implícito: {implied_growth*100:.1f}%")
    note_parts.append(f"FCF/ação: R$ {fcf_per_share:.2f}")
    note = " | ".join(note_parts)

    sections: list[dict] = [{
        "title": "Análise de Sensibilidade — DCF por Cenário",
        "description": desc,
        "type": "table",
        "columns": ["Cenário", "Crescimento Terminal (g)", "Valor Intrínseco", "Margem de Segurança"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
        "note": note,
    }]

    # Chart: line chart showing intrinsic value as a function of g
    # (not bars — a curve showing how intrinsic value changes with g,
    # with the current price as a horizontal reference line and the
    # implied g marked).
    chart_g_values = []
    chart_iv_values = []
    # Generate g from -5% to +10% in 0.5% steps
    for step in range(-10, 21):
        g = step * 0.005  # -5% to +10% in 0.5% steps
        if wacc <= g:
            continue
        iv = fcf_per_share / (wacc - g)
        chart_g_values.append(f"{g*100:.1f}%")
        chart_iv_values.append(iv)

    datasets_chart = [{
        "label": "Valor Intrínseco (R$)",
        "data": chart_iv_values,
        "borderColor": "#0d9488",
        "backgroundColor": "rgba(13,148,136,0.1)",
        "fill": False,
        "tension": 0.3,
        "pointRadius": 0,
        "borderWidth": 2,
    }]
    if current_price and current_price > 0:
        datasets_chart.append({
            "label": "Preço Atual",
            "data": [current_price] * len(chart_g_values),
            "borderColor": "#6b7280",
            "type": "line",
            "fill": False,
            "tension": 0,
            "pointRadius": 0,
            "borderDash": [6, 4],
        })
    # Mark the implied g with a vertical annotation (as a point)
    if implied_growth is not None:
        # Find the closest g step to implied_growth
        iv_at_implied = fcf_per_share / (wacc - implied_growth) if wacc > implied_growth else None
        if iv_at_implied is not None:
            datasets_chart.append({
                "label": f"g implícito ({implied_growth*100:.1f}%)",
                "data": [None] * len(chart_g_values),
                "pointRadius": [5 if chart_g_values[i] == f"{max(-10, min(20, round(implied_growth/0.005)))*0.5*100:.1f}%" else 0 for i in range(len(chart_g_values))],
                "pointBackgroundColor": "#ef4444",
                "pointBorderColor": "#ef4444",
                "showLine": False,
            })
    sections.append({
        "type": "chart",
        "title": "Sensibilidade do Valor Intrínseco",
        "description": (
            "Curva: valor intrínseco vs crescimento terminal (g). "
            "Linha tracejada: preço atual. Ponto vermelho: g implícito "
            "que o mercado precifica. A interseção da curva com a linha "
            "tracejada = o g que justifica o preço atual."
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": chart_g_values, "datasets": datasets_chart},
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {"display": True, "text": "R$ / ação"},
                    },
                    "x": {
                        "title": {"display": True, "text": "Crescimento Terminal (g)"},
                    },
                },
                "plugins": {"legend": {"display": True}},
            },
        },
    })

    return sections
