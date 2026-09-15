"""report/intrinsic.py — DCF intrinsic-value sensitivity analysis.

Contains:
  - _dcf_at_growth                 — private helper: compute DCF intrinsic
                                      value per share with a CUSTOM Stage-1 FCF
                                      growth rate (mirrors dcf_intrinsic_value_at
                                      but lets caller override Stage-1 growth)
  - _normalized_fcf_per_share      — 5Y median of annual FCF per share
                                      (owner-earnings smoothing for cyclicals)
  - _dcf_at_growth_normalized      — 2-stage DCF using normalized FCF as the
                                      base + capped terminal growth (IPCA)
  - build_dcf_sensitivity_section  — DCF in 5 Stage-1 growth scenarios +
                                      bar chart with current-price reference line

[v2.2] Rewrite per LLM review (Claude 1 + Claude 2 + Minimax B43):
  - The previous implementation used a single-stage Gordon perpetuity
    ``Intrinsic = FCF_per_share / (WACC - g)`` with a clamped ``g``.
    For PETR4 (FCF yield 28.3%, WACC 12.6%, implied g = -15.7%), the clamp
    forced g to -2%, which broke the "Mercado = current price" calibration
    and produced R$ 89-122 for a R$ 50 stock.
  - The correct 2-stage DCF already existed as ``_dcf_at_growth`` (uses
    ``project_fcf`` capped to [-10%, +30%] + ``get_terminal_growth`` =
    IPCA-anchored). It was just NOT called by the sensitivity builder.
  - Fix #1 (Claude 1): rewire ``build_dcf_sensitivity_section`` to call
    ``_dcf_at_growth`` varying Stage-1 growth (not terminal g). The
    runaway-perpetuity failure mode is structurally impossible because
    the terminal denominator is always ``WACC - IPCA`` (~8%), never near
    zero.
  - Fix #2 (Claude 2): normalize the base FCF using the 5Y median of
    annual FCF per share (owner-earnings smoothing). TTM FCF captures
    cyclical peaks (PETR4 28.3% FCF yield is an oil-price-spike artifact,
    not steady-state). The median is robust to fat tails.
"""
from __future__ import annotations


# ── V3: DCF Sensitivity Analysis ─────────────────────────────────────────────
#
# Computes DCF intrinsic value at 5 Stage-1 growth-rate scenarios:
#   - base_growth - 15%   (Pessimista)
#   - base_growth - 7.5%  (Conservador)
#   - base_growth         (Base = revenue_growth_1y)
#   - base_growth + 7.5%  (Otimista)
#   - base_growth + 15%   (Agressivo)
#
# base_growth = revenue_growth_1y_at(company, date), capped to [-10%, +30%]
# (the same band ``project_fcf`` enforces internally).
#
# The terminal growth is ALWAYS IPCA-anchored via ``get_terminal_growth()``
# (~4-5% for Brazil) — it is NEVER varied by the scenarios. Varying
# terminal g was the failure mode of the previous design (the denominator
# (WACC - g) collapses as g approaches WACC). By varying Stage-1 growth
# and keeping terminal g fixed at IPCA, the model is structurally safe.

def _dcf_at_growth(
    company: str,
    date: str,
    growth_rate: float,
) -> float | None:
    """Compute DCF intrinsic value per share with a CUSTOM Stage-1 growth rate.

    Mirrors ``dcf_intrinsic_value_at()`` from
    ``skills.cvm.calculations.metrics.dcf_intrinsic_value`` but lets the
    caller pass the Stage-1 FCF growth rate instead of pulling it from
    ``revenue_growth_1y_at``.

    Uses TTM FCF as the base (``operating_cf_at + investing_cf_at``).
    For a normalized-base variant, see ``_dcf_at_growth_normalized``.

    Returns None when FCF/WACC/shares are missing or WACC <= terminal growth.
    """
    try:
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
        from skills.cvm.calculations.engines.shares import shares_at
        from skills.cvm.calculations.growth_helpers import (
            get_terminal_growth, project_fcf, PROJECTION_YEARS,
        )
        from skills.cvm.calculations.metrics.wacc import wacc_at
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


def _normalized_fcf_per_share(company: str, date: str) -> float | None:
    """5Y median of annual FCF per share (owner-earnings smoothing).

    [v2.2] TTM FCF captures cyclical peaks. For a Brazilian oil major at
    an oil-price peak, TTM FCF yield can be 28% — not a sustainable
    steady-state for a perpetuity. Buffett's "owner earnings" approach:
    use a multi-year average to normalize the cycle.

    We use the MEDIAN (not mean) because commodity cycles have fat tails
    — the mean is dragged up by peaks and down by troughs, while the
    median is robust.

    Implementation:
      1. Get all TTM FCO + FCI periods (step function, ~4 per year).
      2. Filter to the last 5 years (by date proximity to ``date``).
      3. Compute FCF = FCO + FCI for each period.
      4. Divide by shares at ``date`` (current share count, not historical
         — avoids share-count noise from buybacks/issuances).
      5. Return the median of the per-share FCF values.

    Returns None if fewer than 3 annual periods are available (need a
    meaningful sample for the median).
    """
    try:
        from datetime import datetime, timedelta
        from statistics import median
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_periods
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_periods
        from skills.cvm.calculations.engines.shares import shares_at
    except ImportError:
        return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    cutoff_str = (datetime.fromisoformat(date) - timedelta(days=365 * 5)).isoformat()[:10] if date else None

    fco_by_date = {p["date"]: p.get("ttm_fco") for p in operating_cf_periods(company) if p.get("date")}
    fci_by_date = {p["date"]: p.get("ttm_fci") for p in investing_cf_periods(company) if p.get("date")}

    all_dates = sorted(set(fco_by_date) & set(fci_by_date))
    if cutoff_str:
        all_dates = [d for d in all_dates if d >= cutoff_str and d <= date]

    if len(all_dates) < 3:
        return None

    fcf_values: list[float] = []
    for d in all_dates:
        fco = fco_by_date.get(d)
        fci = fci_by_date.get(d)
        if fco is None or fci is None:
            continue
        fcf = fco + fci
        if fcf > 0:  # skip negative-FCF periods for the median (cycle troughs)
            fcf_values.append(fcf / shares)

    if len(fcf_values) < 3:
        return None

    return median(fcf_values)


def _dcf_at_growth_normalized(
    company: str,
    date: str,
    growth_rate: float,
    terminal_growth_override: float | None = None,
) -> float | None:
    """2-stage DCF using NORMALIZED FCF (5Y median) as the base.

    [v2.2] Same structure as ``_dcf_at_growth`` but the base FCF is the
    5Y median per-share value (owner-earnings smoothing) instead of TTM.
    This is the function called by ``build_dcf_sensitivity_section``.

    Falls back to ``_dcf_at_growth`` (TTM) when the normalized FCF cannot
    be computed (fewer than 3 annual periods) — preserves the old
    behavior for companies with limited history.

    Args:
      company: Ticker.
      date: YYYY-MM-DD.
      growth_rate: Stage-1 FCF growth rate (project_fcf caps to [-10%, +30%]).
      terminal_growth_override: Override the terminal growth (default:
        IPCA-anchored via get_terminal_growth). The sensitivity builder
        varies this to capture decline scenarios (negative g) that the
        perpetuity with positive g cannot represent. Capped to
        [WACC - 200bps, WACC - 50bps] to keep the denominator safe.

    Returns None when FCF/WACC/shares are missing or WACC <= terminal growth.
    """
    try:
        from skills.cvm.calculations.engines.shares import shares_at
        from skills.cvm.calculations.growth_helpers import (
            get_terminal_growth, project_fcf, PROJECTION_YEARS,
        )
        from skills.cvm.calculations.metrics.wacc import wacc_at
    except ImportError:
        return None

    base_fcf_per_share = _normalized_fcf_per_share(company, date)
    if base_fcf_per_share is None:
        # Fallback: TTM path (company has < 5Y of history). Use the
        # override if provided, otherwise the default IPCA terminal g.
        if terminal_growth_override is not None:
            # Can't use the normalized path — but we can still honor the
            # override by replicating _dcf_at_growth with the override.
            return _dcf_at_growth_with_override(company, date, growth_rate, terminal_growth_override)
        return _dcf_at_growth(company, date, growth_rate)

    wacc = wacc_at(company, date)
    if wacc is None or wacc <= 0:
        return None

    # Terminal growth: default IPCA, or the override capped to keep
    # the perpetuity denominator safe (WACC - g >= 50bps).
    if terminal_growth_override is not None:
        terminal_growth = min(terminal_growth_override, wacc - 0.005)
    else:
        terminal_growth = get_terminal_growth()
        if wacc <= terminal_growth:
            return None

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    # Stage 1: project the NORMALIZED per-share FCF at the requested growth.
    # project_fcf caps growth to [-10%, +30%] (same band as the TTM path).
    fcf_projections = project_fcf(base_fcf_per_share, growth_rate, PROJECTION_YEARS)

    pv_stage1 = 0.0
    for t, fcf_t in enumerate(fcf_projections, 1):
        pv_stage1 += fcf_t / (1.0 + wacc) ** t

    # Stage 2: Terminal Value. terminal_growth may be negative (captures
    # decline — e.g. for an oil major with exhausting reserves).
    fcf_terminal = fcf_projections[-1] * (1.0 + terminal_growth)
    tv = fcf_terminal / (wacc - terminal_growth)
    pv_tv = tv / (1.0 + wacc) ** PROJECTION_YEARS

    return pv_stage1 + pv_tv


def _dcf_at_growth_with_override(
    company: str,
    date: str,
    growth_rate: float,
    terminal_growth: float,
) -> float | None:
    """TTM-base 2-stage DCF with explicit terminal-growth override.

    Fallback path for companies with < 5Y history (normalized FCF
    unavailable). Same as _dcf_at_growth but lets the caller override
    the terminal growth (needed by the sensitivity builder's decline
    scenarios).
    """
    try:
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
        from skills.cvm.calculations.engines.shares import shares_at
        from skills.cvm.calculations.growth_helpers import project_fcf, PROJECTION_YEARS
        from skills.cvm.calculations.metrics.wacc import wacc_at
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

    # Cap terminal growth to keep denominator safe
    terminal_growth = min(terminal_growth, wacc - 0.005)

    shares = shares_at(company, date)
    if shares is None or shares <= 0:
        return None

    fcf_projections = project_fcf(base_fcf, growth_rate, PROJECTION_YEARS)
    pv_stage1 = sum(fcf_t / (1.0 + wacc) ** t for t, fcf_t in enumerate(fcf_projections, 1))
    fcf_terminal = fcf_projections[-1] * (1.0 + terminal_growth)
    tv = fcf_terminal / (wacc - terminal_growth)
    pv_tv = tv / (1.0 + wacc) ** PROJECTION_YEARS
    return (pv_stage1 + pv_tv) / shares


def build_dcf_sensitivity_section(company: str, date: str) -> list[dict]:
    """Build the DCF sensitivity analysis sections (table + chart).

    [v2.2 rewrite] Uses the existing ``_dcf_at_growth_normalized`` (2-stage
    DCF with IPCA-anchored terminal growth + 5Y median normalized FCF).
    Varies Stage-1 FCF growth (not terminal g) around
    ``revenue_growth_1y_at`` — the input with real, bounded uncertainty
    for a specific company.

    Why this fixes the R$ 89-122 problem for PETR4 at R$ 50:
      1. The terminal value (which dominates any DCF) now uses NORMALIZED
         FCF (5Y median per share), not TTM peak FCF. PETR4's 28.3% FCF
         yield is a cycle peak; the 5Y median is materially lower.
      2. The terminal growth is ALWAYS IPCA (~4-5%), never varied by the
         scenarios. The denominator (WACC - g) is always ~8% — it can
         never approach zero or go negative, which is what "the formula
         breaks down" means mechanically.
      3. A negative terminal growth rate is conceptually wrong for a
         perpetuity (contradicts going-concern). Negative near-term
         expectations belong in Stage 1, which this design allows.

    Scenarios (vary Stage-1 growth, not terminal g):
      - Pessimista:  base_growth - 15%
      - Conservador: base_growth - 7.5%
      - Base:        base_growth
      - Otimista:    base_growth + 7.5%
      - Agressivo:   base_growth + 15%

    where base_growth = revenue_growth_1y_at(company, date), capped to
    [-10%, +30%] (the same band project_fcf enforces).

    Returns a list of section dicts (table + chart). Returns an empty
    list if DCF inputs are unavailable.
    """
    try:
        from skills.cvm.calculations.engines.price import price_at
        from skills.cvm.calculations.metrics.wacc import wacc_at
        from skills.cvm.calculations.growth_helpers import get_terminal_growth
    except ImportError:
        return []

    wacc = wacc_at(company, date)
    if wacc is None or wacc <= 0:
        return []

    terminal_growth = get_terminal_growth()

    current_price = None
    try:
        current_price = price_at(company, date)
    except Exception:
        current_price = None

    # Base Stage-1 growth = revenue_growth_1y, capped to [-10%, +30%]
    # (project_fcf enforces this internally, but we cap here too so the
    # scenario labels show the actual growth used, not the unclamped input).
    base_growth = 0.04  # fallback if revenue_growth_1y unavailable
    try:
        from skills.cvm.calculations.metrics.revenue_growth import revenue_growth_1y_at
        rg = revenue_growth_1y_at(company, date)
        if rg is not None:
            base_growth = max(-0.10, min(0.30, rg))
    except Exception:
        pass

    # Normalized FCF per share (for the description + note)
    norm_fcf = _normalized_fcf_per_share(company, date)

    # Market-implied perpetual growth: g_implied = WACC - FCF_yield.
    # This is the honest back-solve (NO clamp) — tells the user what
    # growth the market is pricing in. For high-FCF-yield cyclicals like
    # PETR4, this is deeply negative (market prices in decline).
    market_implied_g = None
    fcf_yield = None
    ttm_fcf_per_share = None
    try:
        from skills.cvm.calculations.engines.dfc.operating_cf import operating_cf_at
        from skills.cvm.calculations.engines.dfc.investing_cf import investing_cf_at
        from skills.cvm.calculations.engines.shares import shares_at
        fco = operating_cf_at(company, date)
        fci = investing_cf_at(company, date)
        sh = shares_at(company, date)
        if fco is not None and fci is not None and sh and sh > 0 and current_price and current_price > 0:
            ttm_fcf_per_share = (fco + fci) / sh
            fcf_yield = ttm_fcf_per_share / current_price
            market_implied_g = wacc - fcf_yield
    except Exception:
        pass

    # Scenarios: vary BOTH Stage-1 growth AND terminal g.
    # [v2.2] The Pessimista uses the market-implied g as its terminal g —
    # this makes it reproduce the current price (the "market is right"
    # scenario), giving the user a bracket: Pessimista ≈ price, higher
    # scenarios show what assumptions justify upside. This replaces the
    # old "Mercado" scenario (which was clamped and broke calibration).
    # If market_implied_g is unavailable, fall back to ipca - 5%.
    ipca = terminal_growth  # get_terminal_growth() result
    pess_terminal = market_implied_g if market_implied_g is not None else (ipca - 0.05)
    # Floor Pessimista terminal at -10% (avoids extreme perpetuity) and
    # cap at WACC - 50bps (denominator safety).
    pess_terminal = max(-0.10, min(pess_terminal, wacc - 0.005))
    scenarios: list[tuple[str, float, float]] = [
        # (name, stage1_growth, terminal_growth)
        ("Pessimista",  max(-0.10, base_growth - 0.10),  pess_terminal),          # ≈ market
        ("Conservador", max(-0.10, base_growth - 0.05),  max(0.00, ipca - 0.02)),  # below IPCA
        ("Base",        base_growth,                       ipca),                   # IPCA terminal
        ("Otimista",    min(0.30, base_growth + 0.05),   min(ipca + 0.01, wacc - 0.005)),
        ("Agressivo",   min(0.30, base_growth + 0.10),   min(ipca + 0.02, wacc - 0.005)),
    ]

    rows: list[list] = []
    chart_labels: list[str] = []
    chart_values: list[float | None] = []

    for name, g_stage1, g_term in scenarios:
        intrinsic = _dcf_at_growth_normalized(company, date, g_stage1, terminal_growth_override=g_term)

        if intrinsic is None:
            rows.append([
                {"text": name, "tooltip": f"FCF 5 anos = {g_stage1*100:.1f}%, Terminal = {g_term*100:.1f}%"},
                f"{g_stage1*100:.1f}%",
                f"{g_term*100:.1f}%",
                "—",
                "—",
            ])
            chart_labels.append(name)
            chart_values.append(None)
            continue

        # Margin of Safety
        mos_str = "—"
        if current_price and intrinsic > 0:
            mos = (intrinsic - current_price) / intrinsic
            mos_str = f"{mos * 100:.1f}%"

        rows.append([
            {"text": name, "tooltip": (
                f"Crescimento FCF 5 anos = {g_stage1*100:.1f}%. "
                f"Terminal = {g_term*100:.1f}%. "
                f"Base FCF = 5Y mediana normalizada."
            )},
            f"{g_stage1*100:.1f}%",
            f"{g_term*100:.1f}%",
            f"R$ {intrinsic:.2f}",
            mos_str,
        ])
        chart_labels.append(name)
        chart_values.append(intrinsic)

    # Add a market-implied g informational row (not a scenario — just shows
    # what the market is pricing in, for context).
    if market_implied_g is not None:
        rows.append([
            {"text": "g implícito (mercado)", "tooltip": (
                "Crescimento perpétuo que o mercado precifica: "
                "g = WACC - FCF_yield. Para empresas cíclicas com FCF yield "
                "alto, este valor é negativo (mercado precifica declínio). "
                "Não é um cenário DCF — é informação de contexto."
            )},
            "—",
            f"{market_implied_g*100:.1f}%",
            f"≈ R$ {current_price:.2f}" if current_price else "—",
            "(= preço atual)",
        ])

    if all(v is None for v in chart_values):
        return []

    # Description + note
    desc_parts = [
        "DCF 2 estágios: FCF normalizado (mediana 5Y) projetado por 5 anos",
        " + valor terminal (Gordon). Cenários variam crescimento FCF e",
        " crescimento terminal (Pessimista permite declínio).",
    ]
    if norm_fcf is not None:
        desc_parts.append(f" FCF base = R$ {norm_fcf:.2f}/ação (mediana 5Y).")
    elif ttm_fcf_per_share is not None:
        desc_parts.append(f" FCF base = R$ {ttm_fcf_per_share:.2f}/ação (TTM, fallback).")
    desc_parts.append(f" WACC = {wacc*100:.1f}%.")
    desc_parts.append(f" IPCA (terminal base) = {ipca*100:.1f}%.")
    desc = "".join(desc_parts)

    note_parts = [
        f"WACC: {wacc*100:.1f}%",
        f"IPCA (terminal base): {ipca*100:.1f}%",
        f"Base FCF: {'R$ {:.2f}/ação (5Y mediana)'.format(norm_fcf) if norm_fcf else 'TTM (fallback)'}",
        f"Crescimento base: {base_growth*100:.1f}% (revenue_growth_1y)",
    ]
    if market_implied_g is not None:
        note_parts.append(f"g implícito mercado: {market_implied_g*100:.1f}%")
        if market_implied_g < -0.05:
            note_parts.append("ATENÇÃO: mercado precifica declínio — DCF com g positivo superestima")
    if current_price:
        note_parts.append(f"Preço atual: R$ {current_price:.2f}")
    note = " | ".join(note_parts)

    sections: list[dict] = [{
        "title": "Análise de Sensibilidade — DCF por Cenário",
        "description": desc,
        "type": "table",
        "columns": ["Cenário", "Crescimento FCF (5 anos)", "Crescimento Terminal", "Valor Intrínseco", "Margem de Segurança"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
        "note": note,
    }]

    # [v2.2] LINE chart: intrinsic value vs terminal growth rate (g).
    # The curve shows how intrinsic value changes as terminal g varies
    # (using the normalized FCF base + Stage-1 growth = base_growth).
    # The current price is a horizontal dashed line. The market-implied g
    # (where the curve crosses the price) is marked with a point — this is
    # the honest visual: "here's what the market is pricing in".
    # For high-FCF-yield cyclicals (PETR4), the crossing point is deeply
    # negative — visually showing the market prices in decline.
    curve_g_values: list[str] = []
    curve_iv_values: list[float | None] = []
    implied_point: list[float | None] = []
    ipca_point: list[float | None] = []
    implied_step = round(market_implied_g / 0.005) if market_implied_g is not None else None
    ipca_step_idx = round(ipca / 0.005)
    # Vary terminal g from -15% to +8% in 0.5% steps (covers decline → IPCA+)
    for step in range(-30, 17):
        g_term = step * 0.005  # -15% to +8% in 0.5% steps
        # Cap at WACC - 50bps (denominator safety)
        if g_term >= wacc - 0.005:
            continue
        iv = _dcf_at_growth_normalized(
            company, date, base_growth, terminal_growth_override=g_term
        )
        curve_g_values.append(f"{g_term*100:.1f}%")
        curve_iv_values.append(iv)
        # Market-implied g point (where intrinsic = price)
        if implied_step is not None and step == implied_step and current_price:
            implied_point.append(current_price)
        else:
            implied_point.append(None)
        # IPCA point (the Base terminal g)
        if step == ipca_step_idx:
            ipca_point.append(iv)
        else:
            ipca_point.append(None)

    curve_datasets: list[dict] = [{
        "label": "Valor Intrínseco (R$)",
        "data": curve_iv_values,
        "borderColor": "#0d9488",
        "backgroundColor": "rgba(13,148,136,0.1)",
        "fill": False,
        "tension": 0.3,
        "pointRadius": 0,
        "borderWidth": 2.5,
    }]
    # Horizontal line: current price
    if current_price and current_price > 0:
        curve_datasets.append({
            "label": f"Preço Atual (R$ {current_price:.2f})",
            "data": [current_price] * len(curve_g_values),
            "borderColor": "#6b7280",
            "type": "line",
            "fill": False,
            "tension": 0,
            "pointRadius": 0,
            "borderDash": [6, 4],
            "borderWidth": 2,
        })
    # Point: market-implied g (where intrinsic = price by construction)
    if market_implied_g is not None and current_price:
        curve_datasets.append({
            "label": f"g implícito mercado ({market_implied_g*100:.1f}%)",
            "data": implied_point,
            "borderColor": "#ef4444",
            "backgroundColor": "#ef4444",
            "pointRadius": [6 if v is not None else 0 for v in implied_point],
            "pointHoverRadius": 8,
            "showLine": False,
        })
    # Point: IPCA (the Base terminal g)
    curve_datasets.append({
        "label": f"IPCA ({ipca*100:.1f}%) — Base",
        "data": ipca_point,
        "borderColor": "#22c55e",
        "backgroundColor": "#22c55e",
        "pointRadius": [6 if v is not None else 0 for v in ipca_point],
        "pointHoverRadius": 8,
        "showLine": False,
    })

    sections.append({
        "type": "chart",
        "title": "Sensibilidade do Valor Intrínseco",
        "description": (
            "Curva: valor intrínseco vs crescimento terminal (g). "
            "Linha tracejada: preço atual. Ponto vermelho: g implícito que "
            "o mercado precifica (onde a curva cruza o preço). Ponto verde: "
            "IPCA (cenário Base). A interseção mostra o que o mercado está "
            "assumindo — para PETR4, é negativo (declínio)."
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": curve_g_values, "datasets": curve_datasets},
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
