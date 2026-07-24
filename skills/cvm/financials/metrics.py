"""skills/cvm/financials/metrics.py -- Ratio computation + standalone quarter derivation.

TWO RESPONSIBILITIES
--------------------
1. Standalone quarter derivation: ITR stores cumulative (Q1=3meses, Q2=6, Q3=9).
   Standalone: Q1=cum3, Q2=cum6-cum3, Q3=cum9-cum6, Q4=DFP12-cum9.
   Snapshots (BPA/BPP) use period-end value directly (no subtraction).

2. Ratio computation: margins, ROA, ROE, EBITDA, debt ratios, payout.

EBITDA FORMULA
--------------
EBITDA = EBIT (DRE 3.05) + Depreciation & Amortization (DFC 6.01.01.02)
The D&A comes from the cash flow statement, not the DRE.

QUARTERLY ROA/ROE
-----------------
For quarterly, ROA/ROE are annualized: (quarterly net income / equity) * 4.
This is a simplification — rapina uses TTM (trailing twelve months) for
some ratios. TTM-based ratios are on the roadmap.

KEY ACCOUNT CODES
-----------------
Summary metrics use these CVM account codes:
  Ativo Total:     1 (BPA, snapshot)
  PL:              2.03 (BPP, snapshot)
  Caixa:           1.01.01 (BPA, snapshot)
  Dívida Bruta:    2.01.04 + 2.02.01 (BPP, snapshot)
  Receita Líquida: 3.01 (DRE, flow)
  Lucro Bruto:     3.03 (DRE, flow)
  EBIT:            3.05 (DRE, flow)
  Resultado Fin.:  3.06 (DRE, flow)
  Lucro Líquido:   3.11 (DRE, flow)
  FCO:             6.01 (DFC, flow)
  FCI:             6.02 (DFC, flow)
  FCF:             6.03 (DFC, flow)
  D&A:             6.01.01.02 (DFC, flow) — for EBITDA
  Proventos:       7.08.04 (DVA, flow) — total dividends+JCP declared
"""

from __future__ import annotations

# ── Key account codes for summary metrics ────────────────────────────────────

SUMMARY_CODES = {
    # BPA (assets — snapshots)
    "1":        ("BPA", "Ativo Total"),
    "1.01.01":  ("BPA", "Caixa e Equivalentes"),
    # BPP (liabilities — snapshots)
    "2":        ("BPP", "Passivo Total"),
    "2.03":     ("BPP", "Patrimônio Líquido"),
    "2.01.04":  ("BPP", "Empréstimos e Financiamentos (Circulante)"),
    "2.02.01":  ("BPP", "Empréstimos e Financiamentos (Não Circulante)"),
    # DRE (income — flows)
    "3.01":     ("DRE", "Receita Líquida"),
    "3.03":     ("DRE", "Lucro Bruto"),
    "3.05":     ("DRE", "EBIT"),
    "3.06":     ("DRE", "Resultado Financeiro"),
    "3.11":     ("DRE", "Lucro/Prejuízo Consolidado"),
    # DFC (cash flow — flows)
    "6.01":     ("DFC_MI", "FCO (Fluxo de Caixa Operacional)"),
    "6.02":     ("DFC_MI", "FCI (Fluxo de Caixa de Investimento)"),
    "6.03":     ("DFC_MI", "FCF (Fluxo de Caixa de Financiamento)"),
    "6.01.01.02": ("DFC_MI", "Depreciação e Amortização"),
    # DVA (value added — flows)
    "7.08.04":  ("DVA", "Remuneração de Capitais Próprios (total)"),
}

# Key codes for `complete` mode (per grupo, not all 497)
KEY_CODES_BY_GRUPO = {
    "BPA":    ["1", "1.01", "1.01.01", "1.01.02", "1.02", "1.02.01"],
    "BPP":    ["2", "2.01", "2.01.04", "2.02", "2.02.01", "2.03", "2.03.01"],
    "DRE":    ["3.01", "3.02", "3.03", "3.04", "3.04.02", "3.05", "3.06", "3.09", "3.11"],
    "DFC_MI": ["6.01", "6.01.01.02", "6.02", "6.03"],
    "DVA":    ["7.08.04", "7.08.04.01", "7.08.04.02"],
}


# ── Standalone quarter derivation ────────────────────────────────────────────

def derive_standalone_quarters(
    cumulative_by_period: dict,
    is_snapshot: bool,
) -> dict:
    """Derive standalone quarterly values from cumulative ITR + DFP data.

    Args:
        cumulative_by_period: {period_label: value} where period_label is
            like "1T2026", "4T2025", etc. Must contain Q1/Q2/Q3 (ITR cumulative)
            and Q4 (DFP annual). Quarters are in DESC order (newest first).
        is_snapshot: True for BPA/BPP (point-in-time — use period-end value
            directly). False for DRE/DFC/DVA (flows — subtract to get standalone).

    Returns:
        {period_label: standalone_value} for each quarter.
    """
    if not cumulative_by_period:
        return {}

    # Sort quarters chronologically (oldest first) for subtraction
    quarters = sorted(cumulative_by_period.keys(), key=_quarter_sort_key)
    result = {}

    for i, q in enumerate(quarters):
        val = cumulative_by_period.get(q)
        if val is None:
            result[q] = None
            continue

        if is_snapshot:
            # Snapshots: use period-end value directly
            result[q] = val
        else:
            # Flows: standalone = this_cumulative - prev_cumulative
            if i == 0:
                # First quarter (oldest) — standalone = cumulative
                result[q] = val
            else:
                prev_q = quarters[i - 1]
                prev_val = cumulative_by_period.get(prev_q)
                if prev_val is not None:
                    result[q] = val - prev_val
                else:
                    result[q] = val  # can't subtract, use cumulative

    return result


def _quarter_sort_key(q: str) -> tuple:
    """Sort key for quarter labels like '1T2026', '4T2025'.
    Returns (year, quarter_num) so chronological order is oldest-first.
    """
    try:
        q_num = int(q[0])  # "1T2026" → 1
        year = int(q[2:])  # "1T2026" → 2026
        return (year, q_num)
    except (ValueError, IndexError):
        return (0, 0)


# ── Ratio computation ────────────────────────────────────────────────────────

def compute_ratios(metrics: dict, is_quarterly: bool = False) -> dict:
    """Compute financial ratios from a metrics dict.

    Args:
        metrics: dict with keys like 'receita_liquida', 'lucro_bruto', 'ebit',
            'ebitda', 'lucro_liquido', 'ativo_total', 'patrimonio_liquido',
            'caixa', 'divida_bruta', 'proventos', 'fco', 'fci', 'fcf'.
        is_quarterly: If True, ROA/ROE are annualized (* 4).

    Returns:
        Dict with computed ratios: marg_bruta, marg_ebitda, marg_ebit,
        marg_liquida, roa, roe, divida_bruta_pl, divida_liquida,
        divida_liquida_pl, payout.
    """
    receita = _f(metrics, "receita_liquida")
    lucro_bruto = _f(metrics, "lucro_bruto")
    ebit = _f(metrics, "ebit")
    ebitda = _f(metrics, "ebitda")
    lucro_liq = _f(metrics, "lucro_liquido")
    ativo = _f(metrics, "ativo_total")
    pl = _f(metrics, "patrimonio_liquido")
    caixa = _f(metrics, "caixa")
    divida_bruta = _f(metrics, "divida_bruta")
    proventos = _f(metrics, "proventos")

    annualize = 4 if is_quarterly else 1

    # Annualized net income for ROA/ROE (None-safe)
    lucro_liq_annualized = lucro_liq * annualize if lucro_liq is not None else None

    ratios = {
        "marg_bruta":   _safe_div(lucro_bruto, receita),
        "marg_ebitda":  _safe_div(ebitda, receita),
        "marg_ebit":    _safe_div(ebit, receita),
        "marg_liquida": _safe_div(lucro_liq, receita),
        "roa":          _safe_div(lucro_liq_annualized, ativo),
        "roe":          _safe_div(lucro_liq_annualized, pl),
        "divida_bruta_pl":     _safe_div(divida_bruta, pl),
        "divida_liquida":      _sub(divida_bruta, caixa),
        "divida_liquida_pl":   None,  # needs divida_liquida / pl
        "payout":              _safe_div(proventos, lucro_liq),
    }
    # Divida liquida / PL
    if ratios["divida_liquida"] is not None and pl:
        ratios["divida_liquida_pl"] = ratios["divida_liquida"] / pl

    return ratios


def compute_ebitda(ebit: float | None, da: float | None) -> float | None:
    """EBITDA = EBIT + Depreciation & Amortization.

    D&A comes from DFC 6.01.01.02. If D&A is missing, EBITDA = EBIT.
    """
    if ebit is None:
        return None
    if da is None:
        return ebit
    return ebit + da


def compute_ttm_ebitda(standalone_ebitda: list) -> float | None:
    """TTM EBITDA = sum of last 4 standalone quarters.

    Args:
        standalone_ebitda: list of EBITDA values, newest-first order.

    Returns:
        TTM EBITDA or None if fewer than 4 quarters available.
    """
    if not standalone_ebitda or len(standalone_ebitda) < 4:
        return None
    vals = [v for v in standalone_ebitda[:4] if v is not None]
    if len(vals) < 4:
        return None
    return sum(vals)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _f(d: dict, key: str) -> float | None:
    """Safely get a float from a dict. Returns None if missing/None."""
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    """Safe division. Returns None if either is None or b is 0."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sub(a: float | None, b: float | None) -> float | None:
    """Safe subtraction. Returns None if either is None."""
    if a is None or b is None:
        return None
    return a - b
