"""skills/cvm/financials/report/analysis.py -- Analytical sections.

Hosts the point-in-time analytical sections that augment the dashboard
(usually appended to the Overview tab or rendered as standalone cards).

Public builders:
  - ``build_red_flags_section(...)`` — accounting consistency checks (BPA/BPP/
    DRE/DVA identities + ROE-with-negative-PL + FCO 3Y decline).
  - ``build_dupont_section(ratios_payload)`` — DuPont 3-step ROE
    decomposition (Net Margin × Asset Turnover × Equity Multiplier).
  - ``build_altman_z_section(ratios_payload)`` — Altman Z-Score bankruptcy
    risk table with zone classification.
  - ``build_wacc_section(ratios_payload)`` — WACC vs ROE/ROIC value-creation
    table.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none


# ── [new commit] F14: Accounting red flags ───────────────────────────────────

def build_red_flags_section(
    bpa_result: dict,
    bpp_result: dict,
    dre_result: dict,
    dfc_result: dict,
    dva_result: dict,
    annual_periods: list[dict],
) -> dict:
    """[new commit] F14 — Accounting red flags (appended to Overview tab).

    Surfaces the cross-statement consistency checks already implemented in
    ``skills/cvm/financials/validation.py`` (BPA 1 ≈ 1.01+1.02; DRE
    3.03 ≈ 3.01-3.02; BPP 2 ≈ 2.01+2.02+2.03; DVA 7.08 ≈ Σ7.08.0x). Each
    statement's periods are checked; mismatches beyond the 5% tolerance
    surface as warnings.

    Also runs two extra checks (computed here, not in validation.py):
      - ROE with negative PL (silent None in metrics.py — flagged here).
      - FCO declining 3Y (earnings-quality red flag).

    Args:
        bpa_result, bpp_result, dre_result, dfc_result, dva_result:
            statement-mode results (each with ``periods`` list).
        annual_periods: list of annual period dicts (for FCO trend check).

    Returns:
        A ``type: "table"`` section with one row per check (pass/fail).
    """
    from skills.cvm.financials.validation import (
        validate_statement_consistency,
    )

    rows: list[list[str]] = []

    def _add_check(label: str, warnings: list[str]) -> None:
        if not warnings:
            rows.append([label, "✓ OK", "—"])
        else:
            # Truncate to first warning for compactness (full text in
            # collapsible below if needed).
            summary = "; ".join(warnings)
            if len(summary) > 220:
                summary = summary[:217] + "..."
            rows.append([label, "⚠ Divergência", summary])

    # Statement consistency checks (validation.py).
    for stmt_result, stmt_type, label in [
        (bpa_result, "bpa", "BPA: 1 = 1.01 + 1.02"),
        (bpp_result, "bpp", "BPP: 2 = 2.01 + 2.02 + 2.03"),
        (dre_result, "dre", "DRE: 3.03 = 3.01 − 3.02"),
        (dva_result, "dva", "DVA: 7.08 = Σ(7.08.01-04)"),
    ]:
        if not isinstance(stmt_result, dict):
            continue
        if stmt_result.get("status") != "ok":
            continue
        periods = stmt_result.get("periods") or []
        warnings = validate_statement_consistency(periods, stmt_type)
        _add_check(label, warnings)

    # Extra check 1: ROE with negative PL.
    pl_warnings: list[str] = []
    if annual_periods:
        for p in annual_periods[:3]:  # latest 3 annual periods
            m = p.get("metrics") or {}
            pl = _num_or_none(m.get("patrimonio_liquido"))
            if pl is not None and pl < 0:
                pl_warnings.append(
                    f"{p.get('period', '?')}: PL negativo "
                    f"({pl:,.0f}) — ROE não é significativo."
                )
    _add_check("ROE: PL positivo (3 últimos anos)", pl_warnings)

    # Extra check 2: FCO declining 3Y (earnings-quality red flag).
    fco_warnings: list[str] = []
    sorted_periods = sorted(
        [p for p in annual_periods if p.get("period")],
        key=lambda p: str(p.get("period")),
    )
    if len(sorted_periods) >= 3:
        # Take last 3 periods (chronological), check FCO trend.
        last3 = sorted_periods[-3:]
        fco_vals = []
        for p in last3:
            m = p.get("metrics") or {}
            fco_vals.append(_num_or_none(m.get("fco")))
        if all(v is not None for v in fco_vals):
            # Flag if FCO strictly declined across all 3 periods.
            if fco_vals[0] > fco_vals[1] > fco_vals[2]:
                fco_warnings.append(
                    f"FCO caiu 3 anos consecutivos: "
                    f"{fco_vals[0]:,.0f} → {fco_vals[1]:,.0f} → "
                    f"{fco_vals[2]:,.0f}. Red flag de qualidade dos lucros."
                )
    _add_check("FCO: tendência 3 anos (não-declínio)", fco_warnings)

    # If no checks ran at all (all statements failed), show empty message.
    if not rows:
        return {
            "type": "collapsible",
            "title": "Red Flags Contábeis",
            "text": "Nenhum dado contábil disponível para validação.",
            "open": False,
        }

    has_warnings = any("⚠" in r[1] for r in rows)
    return {
        "type": "collapsible",
        "title": f"Red Flags Contábeis ({'atenção' if has_warnings else 'OK'})",
        "open": has_warnings,
        "sections": [{
            "title": "Verificações de Consistência Contábil",
            "description": (
                "Cada verificação compara identidades contábeis (e.g., "
                "Ativo = Circulante + Não Circulante) com tolerância de "
                "5%. Divergências podem indicar erro de extração, "
                "arredondamento ou troca de taxonomia (CVM 2012+)."
            ),
            "type": "table",
            "columns": ["Verificação", "Status", "Detalhe"],
            "rows": rows,
        }],
    }


# ── [v2.0] DuPont + Altman Z sections ────────────────────────────────────────

def build_dupont_section(ratios_payload: dict) -> dict | None:
    """Build a DuPont 3-step ROE decomposition section.

    Shows the 3 components (Net Margin, Asset Turnover, Equity Multiplier)
    as a table + bar chart. ROE = Net Margin × Asset Turnover × Equity Multiplier.

    [v2.0] New section for the financials dashboard. Uses ratios_payload
    from compute_all_ratios (point-in-time, no history_fn call).
    """
    from skills.cvm.calculations._registry import METRICS

    # dupont_at returns the ROE float; we need the decomposition components.
    # Call dupont_history for the latest entry to get all 4 components.
    try:
        from skills.cvm.calculations.metrics.dupont import dupont_history
        from datetime import date
        today = date.today().isoformat()
        hist = dupont_history("__PLACEHOLDER__", today, today)  # company passed separately
    except Exception:
        hist = []

    # Actually, dupont_history needs the company. Let's use ratios_payload.
    # The compute_all_ratios call returns dupont_roe (the headline float).
    # For the decomposition, we compute it inline from the engines.
    dupont_roe = ratios_payload.get("dupont_roe")
    if dupont_roe is None:
        return None

    # Get components from ratios_payload if available, else compute from engines
    net_margin = ratios_payload.get("net_margin")
    asset_turnover = ratios_payload.get("asset_turnover")
    # equity_multiplier = total_assets / pl — not in ratios_payload, compute
    # from the dupont_roe / (net_margin * asset_turnover) if both available
    equity_multiplier = None
    if net_margin and asset_turnover and net_margin != 0 and asset_turnover != 0:
        equity_multiplier = dupont_roe / (net_margin * asset_turnover)

    rows = [
        ["Margem Líquida", _fmt(net_margin, "pct")],
        ["Giro do Ativo", _fmt(asset_turnover, "num")],
        ["Multiplicador de Capital", _fmt(equity_multiplier, "num")],
        ["ROE (DuPont)", _fmt(dupont_roe, "pct")],
    ]

    return {
        "title": "DuPont — Decomposição do ROE",
        "description": "ROE = Margem Líquida × Giro do Ativo × Multiplicador de Capital.",
        "type": "table",
        "columns": ["Componente", "Valor"],
        "rows": rows,
        "note": "Mostra como o ROE é composto: eficiência operacional (margem), eficiência de ativos (giro) e alavancagem (multiplicador).",
    }


def build_altman_z_section(
    ratios_payload: dict,
    company: str | None = None,
    today: str | None = None,
) -> dict | None:
    """Build an Altman Z-Score risk section.

    Shows the Z-score + zone classification + 5 X-components as a table.
    Z > 2.99 = safe, 1.81-2.99 = grey, < 1.81 = distress.

    [v2.0] New section for the financials dashboard. Uses ratios_payload
    from compute_all_ratios (point-in-time, no history_fn call).
    [v2.4] Added company+today params to fetch the 5 X-components (X1-X5)
    from altman_z_history. When not provided, falls back to the 2-row table
    (Z-Score + Zona only) for backward compat.
    """
    altman_z = ratios_payload.get("altman_z")
    if altman_z is None:
        return None

    # Zone classification
    if altman_z > 2.99:
        zone = "Seguro (Z > 2.99)"
        zone_color = "#22c55e"
    elif altman_z > 1.81:
        zone = "Cinzento (1.81 - 2.99)"
        zone_color = "#f59e0b"
    else:
        zone = "Risco (< 1.81)"
        zone_color = "#ef4444"

    def _label(text: str, tooltip: str) -> dict:
        return {"text": text, "tooltip": tooltip}

    rows = [
        [_label("Altman Z-Score",
                "Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5"),
         f"{altman_z:.2f}"],
        [_label("Zona",
                "Z > 2.99 seguro, 1.81-2.99 cinzento, < 1.81 risco"),
         zone],
    ]

    # [v2.4] Fetch the 5 X-components from altman_z_history when company+today
    # are provided. This adds the decomposition rows the docstring promised
    # but the v2.0 builder never included.
    x_components = None
    if company and today:
        try:
            from skills.cvm.calculations.metrics.altman_z import altman_z_history
            from datetime import date as _date, timedelta
            date_from = (_date.fromisoformat(today) - timedelta(days=400)).isoformat()
            hist = altman_z_history(company, date_from, today)
            if hist:
                # Take the last entry with non-None z (most recent valid).
                for entry in reversed(hist):
                    if entry.get("altman_z") is not None:
                        x_components = entry
                        break
        except Exception:
            x_components = None

    if x_components:
        rows.append([_label("X1 — Capital de Giro/Ativo",
                            "(Ativo Circ - Passivo Circ) / Ativo Total"),
                     f"{x_components['x1']:.4f}" if x_components.get('x1') is not None else "—"])
        rows.append([_label("X2 — PL/Ativo",
                            "PL / Ativo Total (proxy para Lucros Retidos)"),
                     f"{x_components['x2']:.4f}" if x_components.get('x2') is not None else "—"])
        rows.append([_label("X3 — EBIT/Ativo",
                            "EBIT TTM / Ativo Total"),
                     f"{x_components['x3']:.4f}" if x_components.get('x3') is not None else "—"])
        rows.append([_label("X4 — MktCap/Passivo",
                            "(Preço × Ações) / (Ativo - PL)"),
                     f"{x_components['x4']:.4f}" if x_components.get('x4') is not None else "—"])
        rows.append([_label("X5 — Receita/Ativo",
                            "Receita TTM / Ativo Total"),
                     f"{x_components['x5']:.4f}" if x_components.get('x5') is not None else "—"])

    return {
        "title": "Altman Z-Score — Risco de Falência",
        "description": "Modelo de 1968 para manufatura. Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5.",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
        "note": "X2 usa PL como proxy para lucros retidos (engine BPP 2.03.03+2.03.04 não existe ainda). Interpretar com cautela para empresas não-manufatureiras (bancos, serviços).",
    }


def build_wacc_section(
    ratios_payload: dict,
    company: str | None = None,
    today: str | None = None,
) -> dict | None:
    """Build a WACC (Cost of Capital) section.

    Shows WACC + ROE + ROIC so users can see if the company is creating
    value (ROE/ROIC > WACC = creating value).

    [v2.0] New section for the financials dashboard.
    [v2.4] Added company+today params to fetch the WACC components (COE,
    Kd, E/(D+E), D/(D+E), tax rate) from wacc_history. When not provided,
    falls back to the 4-row table (WACC + ROE + ROIC + Avaliação) for
    backward compat.
    """
    wacc = ratios_payload.get("wacc")
    if wacc is None:
        return None

    roe = ratios_payload.get("roe")
    roic = ratios_payload.get("roic")

    def _label(text: str, tooltip: str) -> dict:
        return {"text": text, "tooltip": tooltip}

    rows = [
        [_label("WACC", "WACC = COE × E/(D+E) + Kd×(1-tax) × D/(D+E)"),
         _fmt(wacc, "pct")],
    ]

    # [v2.4] Fetch WACC components (COE, Kd, weights, tax) from wacc_history
    # when company+today are provided. This implements F15 (WACC drivers
    # decomposition) from the ROADMAP.
    wacc_components = None
    if company and today:
        try:
            from skills.cvm.calculations.metrics.wacc import wacc_history
            from skills.cvm.calculations.metrics.effective_tax_rate import effective_tax_rate_at
            from datetime import date as _date, timedelta
            date_from = (_date.fromisoformat(today) - timedelta(days=400)).isoformat()
            hist = wacc_history(company, date_from, today)
            if hist:
                # Take the last entry with non-None wacc.
                for entry in reversed(hist):
                    if entry.get("wacc") is not None:
                        wacc_components = entry
                        break
            # Tax rate is not in wacc_history output — call directly.
            if wacc_components:
                wacc_components["tax_rate"] = effective_tax_rate_at(company, today)
        except Exception:
            wacc_components = None

    if wacc_components:
        coe = wacc_components.get("coe")
        kd = wacc_components.get("kd")
        weights = wacc_components.get("weights") or {}
        e_weight = weights.get("e_weight")
        d_weight = weights.get("d_weight")
        tax_rate = wacc_components.get("tax_rate")
        rows.append([_label("COE", "Cost of Equity (CAPM: Rf + β × ERP)"),
                     _fmt(coe, "pct") if coe is not None else "—"])
        rows.append([_label("Kd (after-tax)", "Cost of Debt × (1 - tax)"),
                     _fmt(kd, "pct") if kd is not None else "—"])
        rows.append([_label("E/(D+E)", "Peso do Capital Próprio = Market Cap / (D+E)"),
                     _fmt(e_weight, "pct") if e_weight is not None else "—"])
        rows.append([_label("D/(D+E)", "Peso do Capital de Terceiros = Debt / (D+E)"),
                     _fmt(d_weight, "pct") if d_weight is not None else "—"])
        rows.append([_label("Taxa de Imposto", "Taxa efetiva (EBT-based), default 25%"),
                     _fmt(tax_rate, "pct") if tax_rate is not None else "—"])

    rows.append([_label("ROE",  "ROE = Lucro Líquido / Patrimônio Líquido"),
                 _fmt(roe,  "pct")])
    rows.append([_label("ROIC", "ROIC = NOPAT / Capital Investido"),
                 _fmt(roic, "pct")])

    # Value creation assessment
    if roe is not None and wacc is not None:
        spread = roe - wacc
        if spread > 0:
            assessment = f"Criando valor (ROE - WACC = +{spread*100:.1f}%)"
        else:
            assessment = f"Destruindo valor (ROE - WACC = {spread*100:.1f}%)"
        rows.append([
            _label("Avaliação", "Se ROE > WACC, a empresa cria valor"),
            assessment,
        ])

    return {
        "title": "WACC — Custo de Capital vs Retorno",
        "description": "WACC = COE × E/(D+E) + Kd×(1-tax) × D/(D+E). Se ROE/ROIC > WACC, a empresa cria valor.",
        "type": "table",
        "columns": ["Métrica", "Valor"],
        "rows": rows,
        "negative_red": True,
        "positive_green": True,
    }
