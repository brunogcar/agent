"""skills/cvm/financials/metrics.py -- Ratio computation + key account codes.

TWO RESPONSIBILITIES
--------------------
1. Key account codes: SUMMARY_CODES (16 metrics) + KEY_CODES_BY_GRUPO (complete mode).
   [v1.0.1] Now imports the base RESUMO_ACCOUNTS from data_sources catalog to
   avoid two maintained copies that drift.

2. Ratio computation: margins, ROA/ROE, EBITDA, debt ratios, payout.
   [v1.0.1] Negative PL guard — ROE/debt ratios return None when PL <= 0.
   [v1.0.1] Payout = None in quarterly mode (DVA is annual-only).
   [v1.0.1] EBITDA method provenance field (ebit+da / ebit_only / none).

EBITDA FORMULA
--------------
EBITDA = EBIT (DRE 3.05) + Depreciation & Amortization (DFC 6.01.01.02)
The D&A comes from the cash flow statement, not the DRE.

QUARTERLY ROA/ROE
-----------------
For quarterly, ROA/ROE are annualized: (quarterly net income / equity) * 4.
This is a simplification — TTM (trailing twelve months) is on the roadmap.
"""

from __future__ import annotations


# ── Key account codes for summary metrics ────────────────────────────────────
# [v1.0.1] Extended from data_sources/cvm/dfp/catalog.py RESUMO_ACCOUNTS.
# We import the base list and add financials-specific codes (caixa, dívida, D&A, proventos).

def _build_summary_codes():
    """Build SUMMARY_CODES from the catalog's RESUMO_ACCOUNTS + financials extras.

    This avoids maintaining two parallel copies of the CVM account code map.
    The catalog owns the DFP resumo codes; we add skill-specific ones here.
    """
    try:
        from data_sources.cvm.dfp.catalog import RESUMO_ACCOUNTS
        codes = {}
        for code, grupo, label in RESUMO_ACCOUNTS:
            codes[code] = (grupo, label)
    except ImportError:
        # Fallback if catalog import fails (shouldn't happen in production)
        codes = {
            "1":       ("BPA", "Ativo Total"),
            "2":       ("BPP", "Passivo Total"),
            "2.03":    ("BPP", "Patrimônio Líquido"),
            "3.01":    ("DRE", "Receita Líquida"),
            "3.03":    ("DRE", "Lucro Bruto"),
            "3.05":    ("DRE", "EBIT"),
            "3.06":    ("DRE", "Resultado Financeiro"),
            "3.09":    ("DRE", "Resultado Líquido (Operações Continuadas)"),
            "3.11":    ("DRE", "Lucro/Prejuízo Consolidado"),
            "6.01":    ("DFC_MI", "FCO (Fluxo de Caixa Operacional)"),
            "6.02":    ("DFC_MI", "FCI (Fluxo de Caixa de Investimento)"),
            "6.03":    ("DFC_MI", "FCF (Fluxo de Caixa de Financiamento)"),
        }

    # Add financials-specific codes not in RESUMO_ACCOUNTS
    codes["1.01.01"]    = ("BPA", "Caixa e Equivalentes")
    codes["2.01.04"]    = ("BPP", "Empréstimos e Financiamentos (Circulante)")
    codes["2.02.01"]    = ("BPP", "Empréstimos e Financiamentos (Não Circulante)")
    codes["6.01.01.02"] = ("DFC_MI", "Depreciação e Amortização")
    codes["7.08.04"]    = ("DVA", "Remuneração de Capitais Próprios (total)")
    return codes


SUMMARY_CODES = _build_summary_codes()

# Key codes for `complete` mode (per grupo, not all 497)
KEY_CODES_BY_GRUPO = {
    "BPA":    ["1", "1.01", "1.01.01", "1.01.02", "1.02", "1.02.01"],
    "BPP":    ["2", "2.01", "2.01.04", "2.02", "2.02.01", "2.03", "2.03.01"],
    "DRE":    ["3.01", "3.02", "3.03", "3.04", "3.04.02", "3.05", "3.06", "3.09", "3.11"],
    "DFC_MI": ["6.01", "6.01.01.02", "6.02", "6.03"],
    "DVA":    ["7.08.04", "7.08.04.01", "7.08.04.02"],
}


# ── Ratio computation ────────────────────────────────────────────────────────

def compute_ratios(metrics: dict, is_quarterly: bool = False) -> dict:
    """Compute financial ratios from a metrics dict.

    Args:
        metrics: dict with keys like 'receita_liquida', 'lucro_bruto', 'ebit',
            'ebitda', 'lucro_liquido', 'ativo_total', 'patrimonio_liquido',
            'caixa', 'divida_bruta', 'proventos', 'fco', 'fci', 'fcf'.
        is_quarterly: If True, ROA/ROE are annualized (* 4) and payout = None
            (DVA is annual-only, not meaningful per quarter).

    Returns:
        Dict with computed ratios: marg_bruta, marg_ebitda, marg_ebit,
        marg_liquida, roa, roe, divida_bruta_pl, divida_liquida,
        divida_liquida_pl, payout.

    [v1.0.1] Negative PL guard: ROE, divida_bruta_pl, divida_liquida_pl return
    None when PL <= 0 (accumulated losses > capital). ROE with negative PL is
    financially meaningless.

    [v1.0.1] Payout = None in quarterly mode. DVA (7.08.04) is annual-only;
    dividing full-year dividends by a single quarter's net income isn't meaningful.
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

    # [v1.0.1] Negative PL guard — ROE and debt/PL ratios are meaningless
    pl_positive = pl is not None and pl > 0

    # [v1.0.1] Payout = None in quarterly mode (DVA is annual-only)
    payout = None if is_quarterly else _safe_div(proventos, lucro_liq)

    divida_liquida = _sub(divida_bruta, caixa)

    ratios = {
        "marg_bruta":   _safe_div(lucro_bruto, receita),
        "marg_ebitda":  _safe_div(ebitda, receita),
        "marg_ebit":    _safe_div(ebit, receita),
        "marg_liquida": _safe_div(lucro_liq, receita),
        "roa":          _safe_div(lucro_liq_annualized, ativo),
        # [v1.0.1] ROE = None when PL <= 0
        "roe":                   _safe_div(lucro_liq_annualized, pl) if pl_positive else None,
        # [v1.0.1] Debt/PL = None when PL <= 0
        "divida_bruta_pl":       _safe_div(divida_bruta, pl) if pl_positive else None,
        "divida_liquida":        divida_liquida,
        "divida_liquida_pl":     _safe_div(divida_liquida, pl) if (pl_positive and divida_liquida is not None) else None,
        "payout":                payout,
    }

    return ratios


def compute_ebitda(ebit: float | None, da: float | None) -> tuple[float | None, str]:
    """EBITDA = EBIT + Depreciation & Amortization.

    D&A comes from DFC 6.01.01.02. If D&A is missing, EBITDA = EBIT.

    [v1.0.1] Returns (ebitda_value, method) where method is:
      - "ebit+da"  — both EBIT and D&A available, full EBITDA
      - "ebit_only" — D&A missing (DFC_MD filer or no DFC), EBITDA = EBIT
      - "none"     — EBIT missing, can't compute

    Args:
        ebit: EBIT value (DRE 3.05) or None
        da: D&A value (DFC 6.01.01.02) or None

    Returns:
        (ebitda, method) tuple.
    """
    if ebit is None:
        return None, "none"
    if da is None:
        return ebit, "ebit_only"
    return ebit + da, "ebit+da"


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
