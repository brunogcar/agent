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
   [v1.3] Engine-backed variants: compute_ebitda_from_engines() and
   compute_ttm_with_engines() delegate TTM flow metrics to
   skills.cvm.calculations engines (ebit_at, da_at, revenue_at,
   ttm_earnings_at, *_cf_at) instead of summing 4 standalone quarters.
   The legacy sum-of-4-quarters functions (compute_ebitda, compute_ttm)
   are preserved unchanged for callers that don't have a company handle.
   [v1.4] Engine imports are now at MODULE TOP (not lazy inside the two
   *_from_engines / *_with_engines functions). This makes the dependency
   explicit, the engines mockable as `skills.cvm.financials.metrics.ebit_at`,
   and brings the v1.2 hardening (description-search fallback for ebit,
   section-scoping for da) into financials automatically. Ratio
   computation in metrics.py has ZERO direct CVM queries — every flow
   metric goes through the engines.

EBITDA FORMULA
--------------
EBITDA = EBIT (DRE 3.05) + Depreciation & Amortization (DFC 6.01.01.02)
The D&A comes from the cash flow statement, not the DRE.
[v1.3] compute_ebitda_from_engines() fetches EBIT + D&A directly from the
skills.cvm.calculations engines (ebit_at + da_at) instead of receiving
pre-fetched values, with the same ebit_only fallback when D&A is missing.
[v1.4] The hardcoded `3.05` / `6.01.01.02` references in this file are
ONLY in SUMMARY_CODES (for statement rendering) and docstrings — never
used to query CVM directly in ratio computation.

QUARTERLY ROA/ROE
-----------------
For quarterly, ROA/ROE are annualized: (quarterly net income / equity) * 4.
This is a simplification — TTM (trailing twelve months) is on the roadmap.
[v1.3] TODO: migrate to calculations.<engine> when period handling aligns.
The calculations metrics (roa_at, roe_at, *_margin_at) all use TTM
denominators, while financials.compute_ratios() uses standalone quarterly
values (annualized ×4 for ROA/ROE). Different period semantics — not a
clean 1:1 swap.
"""

from __future__ import annotations

# [v1.4-financials-migration] Top-level imports of the calculations engines.
# Previously these were lazy imports inside compute_ebitda_from_engines() and
# compute_ttm_with_engines(). Moving them to module top makes the dependency
# explicit, the engines mockable as `skills.cvm.financials.metrics.ebit_at`,
# and brings the v1.2 hardening (description-search fallback for ebit,
# section-scoping for da) into financials automatically — the engines own
# that logic now.
#
# Auto-discovery side effect: importing any engine module triggers
# skills.cvm.calculations._registry auto-discovery (globs engines/*.py +
# metrics/*.py). Tests set PLANNER_MODEL=test at conftest import time, so
# this is safe in test environments.
from skills.cvm.calculations.engines.ebit import ebit_at
from skills.cvm.calculations.engines.da import da_at
from skills.cvm.calculations.engines.revenue import revenue_at
from skills.cvm.calculations.engines.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.operating_cf import operating_cf_at
from skills.cvm.calculations.engines.investing_cf import investing_cf_at
from skills.cvm.calculations.engines.financing_cf import financing_cf_at


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
    # [v1.9] BPA asset sub-codes — verified against real DFP data (6377-6536
    # rows each). NOT in RESUMO_ACCOUNTS (the catalog stops at 1 / 1.01).
    # Real DFP data confirms:
    #   1.01.03 — Contas a Receber (6389 rows)
    #   1.01.04 — Estoques (6377 rows)
    #   1.02.03 — Imobilizado (6505 rows) — OLD chart (NEW uses 1.07)
    #   1.02.04 — Intangível (6430 rows) — OLD chart (NEW uses 1.08)
    codes["1.01.03"]    = ("BPA", "Contas a Receber")
    codes["1.01.04"]    = ("BPA", "Estoques")
    codes["1.02.03"]    = ("BPA", "Imobilizado")
    codes["1.02.04"]    = ("BPA", "Intangível")
    codes["2.01.04"]    = ("BPP", "Empréstimos e Financiamentos (Circulante)")
    codes["2.02.01"]    = ("BPP", "Empréstimos e Financiamentos (Não Circulante)")
    # [v1.10] BPP liability + equity sub-codes — verified against real DFP
    # data (6355-6579 rows each). NOT in RESUMO_ACCOUNTS (the catalog stops
    # at 2 / 2.03). Real DFP data confirms:
    #   2.01.01 — Fornecedores / Obrigações Sociais / Contas a Pagar
    #             (6476 rows; MULTIPLE descriptions per code — most common
    #             "Obrigações Sociais e Trabalhistas" at 6317 rows; also
    #             "Fornecedores", "Contas a Pagar", "Depósitos")
    #   2.03.01 — Capital Social (6579 rows)
    #   2.03.02 — Reservas de Capital (6558 rows)
    #   2.03.04 — Reservas de Lucros (6480 rows)
    #   2.03.05 — Lucros Acumulados (6453 rows)
    #   2.03.09 — Participação Não Controladores (6355 rows)
    # ⚠️ 2.03 itself has chart-drift: OLD chart = "Patrimônio Líquido" (PL);
    #    NEW chart = "Passivos Financeiros ao Custo Amortizado" (DEBT — not
    #    PL!). 95% of filers (6352/6681 rows) still use the OLD chart, so
    #    the pl engine works for the majority. Documented in BPP.md.
    codes["2.01.01"]    = ("BPP", "Fornecedores / Obrigações")
    codes["2.03.01"]    = ("BPP", "Capital Social")
    codes["2.03.02"]    = ("BPP", "Reservas de Capital")
    codes["2.03.04"]    = ("BPP", "Reservas de Lucros")
    codes["2.03.05"]    = ("BPP", "Lucros Acumulados")
    codes["2.03.09"]    = ("BPP", "Participação Não Controladores")
    # [v1.8] DRE 3.07 — Resultado Líquido das Operações Continuadas. NOT in
    # RESUMO_ACCOUNTS (the catalog stops at 3.06/3.09/3.11). Real DFP data
    # has 6629 rows for 3.07 — it sits between Resultado Financeiro (3.06)
    # and Imposto de Renda (3.08) in the CVM chart of accounts.
    codes["3.07"]       = ("DRE", "Resultado Líquido das Operações Continuadas")
    codes["6.01.01.02"] = ("DFC_MI", "Depreciação e Amortização (Método Indireto)")
    codes["7.08.04"]    = ("DVA", "Remuneração de Capitais Próprios (total)")
    # [v1.2] DFC_MD (direct method) D&A fallback codes — some filers use direct
    # method where D&A is in a different sub-account. We fetch both; the query
    # engine returns whichever exists for a given company.
    codes["6.02.01.02"] = ("DFC_MD", "Depreciação e Amortização (Método Direto)")
    codes["6.01.04"]    = ("DFC_MD", "Depreciação e Amortização (DFC_MD alt)")
    # [v1.7] DVA key metrics — CVM DFP DVA uses 7.xx codes (NOT 1-8).
    # Verified against real DFP: code "7" has 0 rows; "7.08" has data.
    # 7.08 is the dominant format; 7.11 is newer (~75 rows).
    codes["7.08"]     = ("DVA", "Valor Adicionado Total a Distribuir")
    codes["7.08.01"]  = ("DVA", "Pessoal (DVA)")
    codes["7.08.02"]  = ("DVA", "Impostos, Taxas e Contribuições (DVA)")
    codes["7.08.03"]  = ("DVA", "Remuneração de Capital de Terceiros (DVA)")
    # 7.08.04 already added above (Remuneração de Capitais Próprios / proventos)
    return codes


SUMMARY_CODES = _build_summary_codes()

# Key codes for `complete` mode (per grupo, not all 497)
KEY_CODES_BY_GRUPO = {
    # [v1.9] Expanded BPA — covers OLD chart (1.01, 1.02, 1.02.03, 1.02.04)
    # AND NEW chart (1.07 = Imobilizado, 1.08 = Intangível). Codes 1.03-1.06
    # are also included because they exist in real DFP data with multiple
    # descriptions per code (CVM chart drift over years).
    "BPA":    ["1", "1.01", "1.01.01", "1.01.02", "1.01.03", "1.01.04",
               "1.02", "1.02.01", "1.02.03", "1.02.04",
               "1.03", "1.04", "1.05", "1.06", "1.07", "1.08"],
    # [v1.10] Expanded BPP — covers OLD chart (2.01, 2.02, 2.03, 2.03.01-2.03.09)
    # AND NEW chart (2.04=Provisões, 2.05=Passivos Fiscais, 2.06=Outros
    # Passivos, 2.07=Passivos s/ Ativos Não Correntes, 2.08=Patrimônio Líquido
    # — in the NEW chart, 2.03 becomes amortized-cost debt and PL moves to
    # 2.08). 95% of filers (6352/6681 rows) still use OLD chart. Codes 2.xx
    # are unique to BPP (BPA uses 1.xx).
    "BPP":    ["2", "2.01", "2.01.01", "2.01.04", "2.02", "2.02.01",
               "2.03", "2.03.01", "2.03.02", "2.03.04", "2.03.05", "2.03.09",
               "2.04", "2.05", "2.06", "2.07", "2.08"],
    "DRE":    ["3.01", "3.02", "3.03", "3.04", "3.04.02", "3.05", "3.06", "3.07", "3.09", "3.11"],
    "DFC_MI": ["6.01", "6.01.01.02", "6.02", "6.03"],
    # [v1.7] Expanded DVA — CVM DFP uses 7.xx codes (NOT 1-8).
    # Generation side (7.01-7.08) + distribution side (7.08.01-7.08.04)
    # + new format (7.11.01-7.11.04) + existing proventos.
    "DVA":    ["7.01", "7.03", "7.04", "7.05", "7.06", "7.07", "7.08", "7.10",
               "7.08.01", "7.08.02", "7.08.03", "7.08.04",
               "7.11.01", "7.11.02", "7.11.03", "7.11.04",
               "7.08.04.01", "7.08.04.02"],
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

    [v1.3] TODO: migrate to calculations.<metric> when period handling aligns.
    The calculations metrics (roa_at, roe_at, gross_margin_at, etc.) all use
    TTM flow denominators, while this function uses standalone quarterly values
    (annualized ×4 for ROA/ROE in quarterly mode). The period semantics are
    different — a 1:1 swap would change the values. Leave as-is until the
    financials skill adopts TTM as its default period.
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

    [v1.3] For engine-backed variant (fetches EBIT + D&A directly from
    skills.cvm.calculations engines), see compute_ebitda_from_engines().

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


def compute_ebitda_from_engines(company: str, date: str) -> tuple[float | None, str]:
    """EBITDA via calculations engines — ebit_at + da_at with ebit_only fallback.

    [v1.3 migration] Replaces the pre-fetched (ebit, da) parameter pair with
    direct calls to the calculations engines:
      - ebit_at  → DRE 3.05 TTM (with description-search fallback for banks)
      - da_at    → DFC description-search TTM (deprec/amort keywords)

    Same fallback semantics as compute_ebitda():
      - both available  → "ebit+da"
      - D&A missing      → "ebit_only" (EBITDA = EBIT)
      - EBIT missing     → "none"

    Engine failures (FileNotFoundError, missing accounts, etc.) are swallowed
    via _safe_engine_call → None, so a missing DFC database degrades to
    "ebit_only" instead of crashing the caller.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD (TTM window ends at this date).

    Returns:
        (ebitda, method) tuple — same shape as compute_ebitda().
    """
    # [v1.4] ebit_at + da_at are imported at module top — see header comment.
    ebit = _safe_engine_call(ebit_at, company, date)
    if ebit is None:
        return None, "none"
    da = _safe_engine_call(da_at, company, date)
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


def compute_ttm(periods: list[dict]) -> dict:
    """Compute TTM (trailing twelve months) summary from standalone quarters.

    TTM = sum of last 4 standalone quarters for FLOW metrics (revenue, EBIT,
    EBITDA, lucro_liquido, FCO, FCI, D&A, proventos) and average of last 4
    for SNAPSHOT metrics (ativo_total, caixa, PL, divida_bruta).

    Ratios (margins, ROA, ROE) are computed from the TTM flows + average
    snapshots — NOT annualized (×4), which is the v1.1 improvement over v1.0.1.

    [v1.3] For engine-backed variant (fetches TTM flows directly from
    skills.cvm.calculations engines), see compute_ttm_with_engines(). This
    function is preserved unchanged for callers that only have a periods
    list (no company handle).

    Args:
        periods: list of period dicts (newest-first or oldest-first — we sort).
            Each must have {metrics: {...}, ratios: {...}}.

    Returns:
        Dict with TTM metrics + ratios, or {status: "insufficient_data"} if
        fewer than 4 quarters are available.
    """
    if not periods or len(periods) < 4:
        return {"status": "insufficient_data",
                "reason": f"need 4 quarters, got {len(periods) if periods else 0}"}

    # Sort newest-first by (year, quarter) — periods have year + quarter keys
    sorted_periods = sorted(periods,
                            key=lambda p: (p.get("year", 0), p.get("quarter", 0)),
                            reverse=True)
    last4 = sorted_periods[:4]

    # Flow metrics: sum of last 4 standalone quarters
    flow_keys = ["receita_liquida", "lucro_bruto", "ebit", "ebitda",
                 "lucro_liquido", "fco", "fci", "fcf", "da", "proventos"]
    # Snapshot metrics: average of last 4
    snapshot_keys = ["ativo_total", "caixa", "patrimonio_liquido", "divida_bruta"]

    ttm_metrics: dict = {}
    for key in flow_keys:
        vals = []
        for p in last4:
            v = (p.get("metrics") or {}).get(key)
            if v is not None:
                vals.append(float(v))
        ttm_metrics[key] = sum(vals) if len(vals) == 4 else None

    for key in snapshot_keys:
        vals = []
        for p in last4:
            v = (p.get("metrics") or {}).get(key)
            if v is not None:
                vals.append(float(v))
        ttm_metrics[key] = (sum(vals) / len(vals)) if vals else None

    # Compute TTM ratios from the TTM metrics
    ttm_ratios = compute_ratios(ttm_metrics, is_quarterly=False)
    # Override ROA/ROE: TTM lucro_liquido / average snapshot (not annualized)
    # compute_ratios with is_quarterly=False already does:
    #   roa = lucro_liquido / ativo_total
    #   roe = lucro_liquido / patrimonio_liquido
    # which is exactly TTM ROA/ROE. No override needed.

    return {
        "status": "ok",
        "period_range": f"{last4[-1].get('period','?')}–{last4[0].get('period','?')}",
        "metrics": ttm_metrics,
        "ratios": ttm_ratios,
    }


def compute_ttm_with_engines(company: str, date: str, periods: list[dict]) -> dict:
    """TTM via calculations engines for flow metrics + averaged snapshots.

    [v1.3 migration] Replaces the sum-of-4-quarters derivation for FLOW
    metrics with direct calls to skills.cvm.calculations engines:
      - revenue_at      → DRE 3.01 TTM (with description-search fallback)
      - ebit_at         → DRE 3.05 TTM (with description-search fallback)
      - da_at           → DFC description-search TTM (deprec/amort)
      - ttm_earnings_at → DRE 3.11 TTM (with description-search fallback)
      - operating_cf_at → DFC 6.01 TTM
      - investing_cf_at → DFC 6.02 TTM
      - financing_cf_at → DFC 6.03 TTM
      - compute_ebitda_from_engines → ebit_at + da_at (with ebit_only fallback)

    SNAPSHOT metrics (ativo_total, caixa, patrimonio_liquido, divida_bruta)
    continue to use the 4-quarter average from `periods`. The calculations
    engines return a single point-in-time snapshot, which is semantically
    different from the financials skill's averaging approach — averaging
    better smooths quarter-end balance sheet fluctuations.

    Args:
        company: Ticker, name, or CNPJ.
        date: YYYY-MM-DD (typically the end date of the latest quarter —
            TTM window ends at this date).
        periods: list of period dicts (used for snapshot averaging +
            period_range label). Must have at least 4 entries.

    Returns:
        Same structure as compute_ttm():
        {status, period_range, metrics, ratios} on success, or
        {status: "insufficient_data"} if fewer than 4 quarters in `periods`.
    """
    if not periods or len(periods) < 4:
        return {"status": "insufficient_data",
                "reason": f"need 4 quarters, got {len(periods) if periods else 0}"}

    # [v1.4] All engines are imported at module top — see header comment.

    # Sort newest-first by (year, quarter) for snapshot averaging + label
    sorted_periods = sorted(periods,
                            key=lambda p: (p.get("year", 0), p.get("quarter", 0)),
                            reverse=True)
    last4 = sorted_periods[:4]

    # Snapshot metrics: average of last 4 (same as compute_ttm)
    snapshot_keys = ["ativo_total", "caixa", "patrimonio_liquido", "divida_bruta"]
    ttm_metrics: dict = {}
    for key in snapshot_keys:
        vals = []
        for p in last4:
            v = (p.get("metrics") or {}).get(key)
            if v is not None:
                vals.append(float(v))
        ttm_metrics[key] = (sum(vals) / len(vals)) if vals else None

    # Flow metrics: use calculations engines (TTM derivation is DFP-ITR+ITR,
    # mathematically equivalent to sum-of-4-standalone-quarters but fetched
    # directly from the engine layer).
    ttm_metrics["receita_liquida"] = _safe_engine_call(revenue_at, company, date)
    ttm_metrics["ebit"]            = _safe_engine_call(ebit_at, company, date)
    ttm_metrics["da"]              = _safe_engine_call(da_at, company, date)
    ttm_metrics["lucro_liquido"]   = _safe_engine_call(ttm_earnings_at, company, date)
    ttm_metrics["fco"]             = _safe_engine_call(operating_cf_at, company, date)
    ttm_metrics["fci"]             = _safe_engine_call(investing_cf_at, company, date)
    ttm_metrics["fcf"]             = _safe_engine_call(financing_cf_at, company, date)
    # EBITDA from engines with ebit_only fallback when D&A missing
    ttm_metrics["ebitda"], ttm_metrics["ebitda_method"] = compute_ebitda_from_engines(
        company, date)

    # Flow metrics without a clean engine mapping: fall back to sum-of-4.
    # TODO: migrate to calculations.<engine> when one is added for these.
    for key in ("lucro_bruto", "proventos"):
        vals = []
        for p in last4:
            v = (p.get("metrics") or {}).get(key)
            if v is not None:
                vals.append(float(v))
        ttm_metrics[key] = sum(vals) if len(vals) == 4 else None

    # Compute TTM ratios from the TTM metrics (same as compute_ttm)
    ttm_ratios = compute_ratios(ttm_metrics, is_quarterly=False)

    return {
        "status": "ok",
        "period_range": f"{last4[-1].get('period','?')}–{last4[0].get('period','?')}",
        "metrics": ttm_metrics,
        "ratios": ttm_ratios,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_engine_call(fn, *args, **kwargs):
    """Call a calculations engine and return None on any error.

    Same pattern as financials.financials._safe_call — calculations engines
    call connect_dfp/connect_itr which may raise FileNotFoundError when the
    underlying DB is not synced, and individual accounts may be missing for
    some filers. Without this wrapper, one missing DB or account would
    propagate up and crash the caller (compute_ttm_with_engines,
    compute_ebitda_from_engines).
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


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
