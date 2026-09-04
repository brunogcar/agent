"""skills/cvm/financials/report/comprehensive.py -- Comprehensive period table.

[v14] New builder for the Períodos/Séries Temporais tabs. Replaces the
simple 7-column tables (Receita/EBIT/EBITDA/Lucro/Margens) with a
comprehensive multi-section table matching the user's Google Sheets
layout.

The table has 4 sections, each with a section header row:
  1. Balanço Patrimonial (11 rows)
  2. Demonstrativo de Resultado (4 rows)
  3. Fluxo de Caixa (8 rows)
  4. Indicadores Fundamentalistas (21 rows)

Periods are columns (newest first). Uses the ``wide=True`` flag so the
frozen Código + Descrição columns + section header sticky CSS applies.

Data sources (reuses already-fetched data — no new engine calls):
  - ``annual_periods`` / ``quarterly_periods`` / ``ttm_periods``: have
    ``metrics`` (pre-computed: receita, ebit, ebitda, lucro, fco, fci, fcf)
    + ``ratios`` (pre-computed: marg_bruta, marg_ebit, marg_ebitda,
    marg_liquida, etc.)
  - ``bpa_result`` / ``bpp_result`` / ``dre_result`` / ``dfc_result``:
    have ``accounts`` dicts with raw line items (Ativo Circulante 1.01,
    Estoques 1.01.03, Passivo Circulante 2.01, Fornecedores 2.01.01,
    Capital Social 2.03.01, etc.)

The builder merges these by period label. Missing values show "—".

Future: as more engines/metrics are added, this table can be extended
by adding rows to the _COMPREHENSIVE_ROWS config + the matching extract
logic in _extract_value.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _fmt, _num_or_none, _pct_of


# ── Row definitions ──────────────────────────────────────────────────────────
# Each row: (label, section, source, key, format_spec)
# source = "metrics" (from annual/quarterly/ttm periods), "ratios" (from
# periods), "accounts" (from statement results — needs code), or "computed"
# (computed inline from other values).
# format_spec = "brl" (compact BRL), "pct" (percentage), "num" (ratio number).

_COMPREHENSIVE_ROWS = [
    # ── Section 1: Balanço Patrimonial ──────────────────────────────
    ("Ativo Total",                  "Balanço Patrimonial", "accounts", "1",      "brl"),
    ("Ativo Circulante",             "Balanço Patrimonial", "accounts", "1.01",   "brl"),
    ("Estoques",                     "Balanço Patrimonial", "accounts", "1.01.03","brl"),
    ("Ativo Não Circulante",         "Balanço Patrimonial", "accounts", "1.02",   "brl"),
    ("Passivo Total",                "Balanço Patrimonial", "accounts", "2",      "brl"),
    ("Passivo Circulante",           "Balanço Patrimonial", "accounts", "2.01",   "brl"),
    ("Fornecedores",                 "Balanço Patrimonial", "accounts", "2.01.01","brl"),
    ("Passivo Não Circulante",       "Balanço Patrimonial", "accounts", "2.02",   "brl"),
    ("Patrimônio Líquido",           "Balanço Patrimonial", "accounts", "2.03",              "brl"),
    ("Part. Acionistas NC",          "Balanço Patrimonial", "accounts", "2.03.02","brl"),
    ("Capital Social Realizado",     "Balanço Patrimonial", "accounts", "2.03.01","brl"),

    # ── Section 2: Demonstrativo de Resultado ──────────────────────
    ("Receitas",                     "Demonstrativo de Resultado", "metrics", "receita_liquida", "brl"),
    ("Resultado Bruto",              "Demonstrativo de Resultado", "metrics", "lucro_bruto",     "brl"),
    ("Atribuído a Sócios NC",        "Demonstrativo de Resultado", "accounts", "3.09.02",        "brl"),
    ("Lucro Líquido Consolidado",    "Demonstrativo de Resultado", "metrics", "lucro_liquido",   "brl"),

    # ── Section 3: Fluxo de Caixa ──────────────────────────────────
    ("FCO",                          "Fluxo de Caixa", "metrics", "fco", "brl"),
    ("Depreciação/Amortização",      "Fluxo de Caixa", "metrics", "da",  "brl"),
    ("FCI",                          "Fluxo de Caixa", "metrics", "fci", "brl"),
    ("FCF",                          "Fluxo de Caixa", "metrics", "fcf", "brl"),
    ("FCT",                          "Fluxo de Caixa", "computed", "fct", "brl"),  # FCO+FCI+FCF
    ("FCL",                          "Fluxo de Caixa", "computed", "fcl", "brl"),  # FCO - |CAPEX|
    ("Saldo Inicial",                "Fluxo de Caixa", "accounts", "6.01.01", "brl"),  # [v14] best-effort
    ("Saldo Final",                  "Fluxo de Caixa", "computed", "saldo_final", "brl"),  # Saldo Inicial + FCT

    # ── Section 4: Crescimento ─────────────────────────────────────
    ("Cres. RL (Período Anterior)",  "Crescimento", "computed", "cres_rl", "pct"),
    ("Cres. RB (Período Anterior)",  "Crescimento", "computed", "cres_rb", "pct"),
    ("Cres. LL (Período Anterior)",  "Crescimento", "computed", "cres_ll", "pct"),

    # ── Section 5: CAGR ────────────────────────────────────────────
    ("CAGR RL (5 Períodos)",         "CAGR", "computed", "cagr_rl", "pct"),
    ("CAGR RB (5 Períodos)",         "CAGR", "computed", "cagr_rb", "pct"),
    ("CAGR LL (5 Períodos)",         "CAGR", "computed", "cagr_ll", "pct"),

    # ── Section 6: Margens ─────────────────────────────────────────
    ("Marg. Bruta",                  "Margens", "ratios", "marg_bruta",   "pct"),
    ("Marg. EBIT",                   "Margens", "ratios", "marg_ebit",    "pct"),
    ("Marg. EBITDA",                 "Margens", "ratios", "marg_ebitda",  "pct"),
    ("Marg. Líquida",                "Margens", "ratios", "marg_liquida", "pct"),

    # ── Section 7: Liquidez e Alavancagem ──────────────────────────
    ("Giro Ativos",                  "Liquidez e Alavancagem", "computed", "giro_ativos",     "num"),
    ("Liquidez Corrente",            "Liquidez e Alavancagem", "computed", "liquidez_corrente","num"),
    ("Liquidez Imediata",            "Liquidez e Alavancagem", "computed", "liquidez_imediata","num"),
    ("Div Br / Patrim",              "Liquidez e Alavancagem", "computed", "div_br_patrim",   "num"),

    # ── Section 8: Disponibilidades e Endividamento ────────────────
    ("Disponibilidades",             "Disponibilidades e Endividamento", "accounts", "1.01.01",      "brl"),
    ("Dív. Bruta",                   "Disponibilidades e Endividamento", "computed", "divida_bruta",  "brl"),
    ("Dív. Líquida",                 "Disponibilidades e Endividamento", "computed", "divida_liquida", "brl"),
    ("Capital Giro",                 "Disponibilidades e Endividamento", "computed", "capital_giro",  "brl"),

    # ── Section 9: EBIT, EBITDA e CAPEX ────────────────────────────
    ("EBIT",                         "EBIT, EBITDA e CAPEX", "metrics", "ebit",          "brl"),
    ("EBITDA",                       "EBIT, EBITDA e CAPEX", "metrics", "ebitda",        "brl"),
    ("CAPEX",                        "EBIT, EBITDA e CAPEX", "capex_engine", "capex",     "brl"),  # [v2.4] real capex engine, fallback to FCI
]


def _get_account_value(accounts, codigo: str) -> float | None:
    """Extract a value from a statement accounts structure by codigo.

    Handles BOTH formats:
      - List of dicts: [{"codigo": "1", "valor_brl": 500000}, ...]
      - Dict keyed by codigo: {"1": 500000, "1.01": 100000, ...}
    Returns the first match, or None.
    """
    if not accounts:
        return None
    # Format 1: dict keyed by codigo → {codigo: valor} or {codigo: {valor_brl: ...}}
    if isinstance(accounts, dict):
        v = accounts.get(codigo)
        if v is None:
            return None
        # Could be a plain number or a dict with valor_brl key (reshaped format)
        if isinstance(v, dict):
            v = v.get("valor_brl")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    # Format 2: list of dicts → [{"codigo": ..., "valor_brl": ...}, ...]
    for acc in accounts:
        if isinstance(acc, dict) and acc.get("codigo") == codigo:
            v = acc.get("valor_brl")
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
    return None


def _build_accounts_by_period(result: dict) -> dict:
    """Build a {period_label: accounts} dict from a statement result.

    [v20] Indexes by MULTIPLE labels so matching works across different
    period dict shapes:
      - Annual summary: "period": "2025"
      - Annual statement (reshaped): "period": None, "data_fim_exerc": "2025-12-31"
      - Quarterly: "period": "2T2026"
      - TTM: "quarter": "2T2026"
    
    For each period, we add entries for:
      1. "period" or "quarter" (e.g. "2025", "2T2026")
      2. "data_fim_exerc" (e.g. "2025-12-31")
      3. year extracted from data_fim_exerc (e.g. "2025" from "2025-12-31")
    So the comprehensive table's period labels can match any of these.
    """
    by_period = {}
    if not result or result.get("status") != "ok":
        return by_period
    for p in result.get("periods") or []:
        accounts = p.get("accounts") or []
        # Label 1: period or quarter
        label1 = p.get("period") or p.get("quarter") or ""
        if label1:
            by_period[str(label1)] = accounts
        # Label 2: data_fim_exerc (full date)
        label2 = p.get("data_fim_exerc") or ""
        if label2:
            by_period[str(label2)] = accounts
            # Label 3: year extracted from date (e.g. "2025" from "2025-12-31")
            year = str(label2)[:4]
            if year and len(year) == 4:
                by_period[year] = accounts
        # Label 4: year as int → str (e.g. 2025 → "2025")
        if p.get("year"):
            by_period[str(p["year"])] = accounts
    return by_period


def _extract_value(
    row_def: tuple,
    period: dict,
    bpa_acc,
    bpp_acc,
    dre_acc,
    dfc_acc,
    all_periods: list,
    period_idx: int,
    capex_map: dict | None = None,
) -> float | None:
    """Extract a single value for one row + one period.

    [v18] Added metrics fallback for accounts-based rows. When accounts
    aren't available (e.g., YoY periods), try the metrics dict instead.
    Also pass quarterly statement results for YoY account lookups.

    [v2.4] Added ``capex_engine`` source — looks up the real CapEx value
    (from ``capex_periods()``) in ``capex_map`` keyed by period label.
    Falls back to ``metrics["fci"]`` (the old proxy) when the engine
    returns None or ``capex_map`` is not provided. CapEx is negative
    (outflow) in the engine — returns ``abs()`` so the table reads as
    "spent on capex" (positive value).

    Args:
        row_def: (label, section, source, key, format) tuple.
        period: the period dict (has 'metrics', 'ratios').
        bpa_acc/bpp_acc/dre_acc/dfc_acc: the accounts for this period.
        all_periods: all periods (for computing growth/CAGR).
        period_idx: index of current period in all_periods.
        capex_map: optional {period_label: capex_value} dict from
            ``capex_periods()``. None → CAPEX row falls back to FCI proxy.

    Returns: float value or None.
    """
    label, section, source, key, fmt = row_def
    m = period.get("metrics") or {}
    r = period.get("ratios") or {}

    if source == "metrics":
        return _num_or_none(m.get(key))

    elif source == "ratios":
        return _num_or_none(r.get(key))

    elif source == "capex_engine":
        # [v2.4] Real CapEx from the capex_at engine (description-search:
        # imobilizado/intangivel, scoped to DFC 6.02.%, excludes baixa/
        # alienacao disposal lines, TTM-derived from DFP + ITR). Falls
        # back to FCI (total investing cash flow) when the engine returns
        # None or capex_map is not provided. CapEx is negative (outflow)
        # in the engine — return abs() so the table reads as "spent".
        # [v2 fix] Quarterly mode periods have year+quarter but NOT
        # data_fim_exerc — compute it from year+quarter so the lookup
        # matches the ITR date in capex_map (e.g. "2T2026" → "2026-06-30").
        if capex_map:
            period_label = (
                str(period.get("period") or period.get("quarter") or "")
            )
            date_label = str(period.get("data_fim_exerc") or "")
            year_label = str(period.get("year") or "")
            # [v2 fix] Compute data_fim_exerc from year+quarter when missing.
            # Quarterly mode periods have year+quarter but no data_fim_exerc.
            if not date_label and year_label:
                quarter_num = period.get("quarter")
                if quarter_num is not None:
                    month_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
                    try:
                        me = month_end.get(int(quarter_num))
                    except (TypeError, ValueError):
                        me = None
                    if me:
                        date_label = f"{year_label}-{me}"
            # Year extracted from data_fim_exerc (e.g. "2025" from "2025-12-31")
            year_from_date = date_label[:4] if len(date_label) >= 4 else ""
            for lookup_key in (date_label, period_label, year_label, year_from_date):
                if lookup_key and lookup_key in capex_map:
                    val = capex_map[lookup_key]
                    if val is not None:
                        return abs(_num_or_none(val))
        # Fallback: FCI proxy (total investing cash flow — includes
        # acquisitions of subsidiaries, loans made, etc. — NOT just capex).
        return _num_or_none(m.get("fci"))

    elif source == "accounts":
        # [v18] Try accounts first, then metrics as fallback.
        # Many account codes have a corresponding metrics key.
        _ACCOUNT_TO_METRIC = {
            "1":       "ativo_total",
            "2":       None,  # Passivo Total — no metrics equivalent
            "1.01":    None,  # Ativo Circ — no metrics equivalent
            "1.01.03": None,  # Estoques — no metrics equivalent
            "1.02":    None,  # Ativo Não Circ — no metrics equivalent
            "2.01":    None,  # Passivo Circ — no metrics equivalent
            "2.01.01": None,  # Fornecedores — no metrics equivalent
            "2.02":    None,  # Passivo Não Circ — no metrics equivalent
            "2.03":   "patrimonio_liquido",  # PL — metrics fallback
            "2.03.01": None,  # Capital Social — no metrics equivalent
            "1.01.01": "caixa",  # Caixa — metrics fallback
            "2.03.02": None,  # Part. Acionistas NC — no metrics equivalent
            "3.09.02": None,  # Atribuído a Sócios NC — no metrics equivalent
            "6.01.01": None,  # Saldo Inicial — no metrics equivalent
        }
        # Try accounts
        if key.startswith("1"):
            val = _get_account_value(bpa_acc, key)
        elif key.startswith("2"):
            val = _get_account_value(bpp_acc, key)
        elif key.startswith("3"):
            val = _get_account_value(dre_acc, key)
        elif key.startswith("6"):
            val = _get_account_value(dfc_acc, key)
        else:
            val = None
        # Fallback to metrics if available
        if val is None:
            metric_key = _ACCOUNT_TO_METRIC.get(key)
            if metric_key:
                val = _num_or_none(m.get(metric_key))
        return val

    elif source == "computed":
        if key == "fct":
            fco = _num_or_none(m.get("fco"))
            fci = _num_or_none(m.get("fci"))
            fcf = _num_or_none(m.get("fcf"))
            if fco is not None and fci is not None and fcf is not None:
                return fco + fci + fcf
            return None

        elif key == "fcl":
            fco = _num_or_none(m.get("fco"))
            fci = _num_or_none(m.get("fci"))
            if fco is not None and fci is not None:
                return fco + fci
            return None

        elif key == "saldo_final":
            saldo_inicial = _get_account_value(dfc_acc, "6.01.01")
            fco = _num_or_none(m.get("fco"))
            fci = _num_or_none(m.get("fci"))
            fcf = _num_or_none(m.get("fcf"))
            if saldo_inicial is not None and fco is not None and fci is not None and fcf is not None:
                return saldo_inicial + fco + fci + fcf
            return None

        elif key == "cres_rl":
            curr = _num_or_none(m.get("receita_liquida"))
            if period_idx + 1 < len(all_periods):
                prev_m = all_periods[period_idx + 1].get("metrics") or {}
                prev = _num_or_none(prev_m.get("receita_liquida"))
                if curr is not None and prev is not None and prev != 0:
                    return (curr - prev) / abs(prev)
            return None

        elif key == "cres_rb":
            curr = _num_or_none(m.get("lucro_bruto"))
            if period_idx + 1 < len(all_periods):
                prev_m = all_periods[period_idx + 1].get("metrics") or {}
                prev = _num_or_none(prev_m.get("lucro_bruto"))
                if curr is not None and prev is not None and prev != 0:
                    return (curr - prev) / abs(prev)
            return None

        elif key == "cres_ll":
            curr = _num_or_none(m.get("lucro_liquido"))
            if period_idx + 1 < len(all_periods):
                prev_m = all_periods[period_idx + 1].get("metrics") or {}
                prev = _num_or_none(prev_m.get("lucro_liquido"))
                if curr is not None and prev is not None and prev != 0:
                    return (curr - prev) / abs(prev)
            return None

        elif key == "cagr_rl":
            curr = _num_or_none(m.get("receita_liquida"))
            if period_idx + 4 < len(all_periods):
                base_m = all_periods[period_idx + 4].get("metrics") or {}
                base = _num_or_none(base_m.get("receita_liquida"))
                if curr is not None and base is not None and base > 0 and curr > 0:
                    return (curr / base) ** (1.0 / 4) - 1
            return None

        elif key == "cagr_rb":
            curr = _num_or_none(m.get("lucro_bruto"))
            if period_idx + 4 < len(all_periods):
                base_m = all_periods[period_idx + 4].get("metrics") or {}
                base = _num_or_none(base_m.get("lucro_bruto"))
                if curr is not None and base is not None and base > 0 and curr > 0:
                    return (curr / base) ** (1.0 / 4) - 1
            return None

        elif key == "cagr_ll":
            curr = _num_or_none(m.get("lucro_liquido"))
            if period_idx + 4 < len(all_periods):
                base_m = all_periods[period_idx + 4].get("metrics") or {}
                base = _num_or_none(base_m.get("lucro_liquido"))
                if curr is not None and base is not None and base > 0 and curr > 0:
                    return (curr / base) ** (1.0 / 4) - 1
            return None

        elif key == "divida_bruta":
            # [v22] Dív. Bruta from accounts (2.01.04 + 2.02.01) with metrics fallback
            d_circ = _get_account_value(bpp_acc, "2.01.04")
            d_ncirc = _get_account_value(bpp_acc, "2.02.01")
            if d_circ is not None or d_ncirc is not None:
                return (d_circ or 0) + (d_ncirc or 0)
            return _num_or_none(m.get("divida_bruta"))

        elif key == "divida_liquida":
            # [v23] Use accounts with metrics fallback for Q1-Q3 (ITR)
            d_circ = _get_account_value(bpp_acc, "2.01.04")
            d_ncirc = _get_account_value(bpp_acc, "2.02.01")
            db = (d_circ or 0) + (d_ncirc or 0) if (d_circ is not None or d_ncirc is not None) else _num_or_none(m.get("divida_bruta"))
            caixa_acc = _get_account_value(bpa_acc, "1.01.01")
            caixa = caixa_acc if caixa_acc is not None else _num_or_none(m.get("caixa"))
            if db is not None and caixa is not None:
                return db - caixa
            return None

        elif key == "capital_giro":
            # [v18] Try accounts first, then compute from metrics
            ac = _get_account_value(bpa_acc, "1.01")
            pc = _get_account_value(bpp_acc, "2.01")
            if ac is not None and pc is not None:
                return ac - pc
            return None

        elif key == "giro_ativos":
            # [v18] Giro Ativos = Receita / Ativo Total
            # Use metrics["ativo_total"] as fallback when accounts missing
            receita = _num_or_none(m.get("receita_liquida"))
            ativo = _get_account_value(bpa_acc, "1")
            if ativo is None:
                ativo = _num_or_none(m.get("ativo_total"))
            if receita is not None and ativo is not None and ativo != 0:
                return receita / ativo
            return None

        elif key == "liquidez_corrente":
            # [v18] Liquidez Corrente = Ativo Circ / Passivo Circ
            # Needs accounts — no metrics fallback available
            ac = _get_account_value(bpa_acc, "1.01")
            pc = _get_account_value(bpp_acc, "2.01")
            if ac is not None and pc is not None and pc != 0:
                return ac / pc
            return None

        elif key == "liquidez_imediata":
            # [v23] Use accounts (1.01.01) with metrics fallback for Q1-Q3 (ITR)
            caixa_acc = _get_account_value(bpa_acc, "1.01.01")
            caixa = caixa_acc if caixa_acc is not None else _num_or_none(m.get("caixa"))
            pc = _get_account_value(bpp_acc, "2.01")
            if caixa is not None and pc is not None and pc != 0:
                return caixa / pc
            return None

        elif key == "div_br_patrim":
            # [v23] Use accounts with metrics fallback for Q1-Q3 (ITR)
            d_circ = _get_account_value(bpp_acc, "2.01.04")
            d_ncirc = _get_account_value(bpp_acc, "2.02.01")
            db = (d_circ or 0) + (d_ncirc or 0) if (d_circ is not None or d_ncirc is not None) else _num_or_none(m.get("divida_bruta"))
            pl_acc = _get_account_value(bpp_acc, "2.03")
            pl = pl_acc if pl_acc is not None else _num_or_none(m.get("patrimonio_liquido"))
            if db is not None and pl is not None and pl != 0:
                return db / pl
            return None

        return None

    return None


def build_comprehensive_period_table(
    periods: list[dict],
    label: str,
    bpa_result: dict | None = None,
    bpp_result: dict | None = None,
    dre_result: dict | None = None,
    dfc_result: dict | None = None,
    capex_map: dict | None = None,
) -> dict:
    """[v14] Build a comprehensive multi-section period table.

    Matches the user's Google Sheets layout: ~35 metric rows grouped by
    4 section headers (Balanço, DRE, DFC, Indicadores), periods as columns
    (newest first).

    [v2.4] Added ``capex_map`` kwarg — a {period_label: capex_value} dict
    from ``capex_periods()``. When provided, the CAPEX row uses the real
    CapEx engine value (description-search: imobilizado/intangivel, scoped
    to DFC 6.02.%, TTM-derived). Falls back to FCI proxy when the engine
    returns None or capex_map is not provided (backward-compatible).

    Args:
        periods: list of period dicts (annual, quarterly, or TTM). Each
            must have 'period' label + 'metrics' + 'ratios' dicts.
        label: "Anual", "Trimestral", or "Anualizado" — used in the title.
        bpa_result/bpp_result/dre_result/dfc_result: statement results
            with 'accounts' dicts for raw line items. When None, the
            corresponding section rows show "—" for account-based values.
        capex_map: optional {period_label: capex_value} dict from
            ``capex_periods()``. None → CAPEX row falls back to FCI proxy.

    Returns:
        A type:"table" section dict with wide=True (frozen columns).
    """
    if not periods:
        return {
            "title": f"{label} — Dados indisponíveis",
            "type": "text",
            "text": f"Dados {label.lower()} indisponíveis para esta empresa.",
        }

    # Sort newest-first (periods may already be sorted, but ensure it).
    def _sort_key(p):
        # [v17] TTM periods use "quarter" key, not "period". Check both.
        period = str(p.get("period") or p.get("quarter") or "")
        if "T" in period:
            try:
                q = int(period.split("T")[0])
                y = int(period.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                return (0, 0)
        try:
            return (int(period), 0)
        except ValueError:
            return (0, 0, period)

    sorted_periods = sorted(periods, key=_sort_key, reverse=True)
    n_periods = len(sorted_periods)
    period_labels = [str(p.get("period") or p.get("quarter") or "—") for p in sorted_periods]

    # Build accounts-by-period lookups for each statement.
    bpa_by_period = _build_accounts_by_period(bpa_result)
    bpp_by_period = _build_accounts_by_period(bpp_result)
    dre_by_period = _build_accounts_by_period(dre_result)
    dfc_by_period = _build_accounts_by_period(dfc_result)

    # [v16] Build 4 separate tables (one per section) instead of one big table.
    # Group rows by section.
    from collections import OrderedDict
    sections_map = OrderedDict()
    for row_def in _COMPREHENSIVE_ROWS:
        metric_label, section, source, key, fmt = row_def
        if section not in sections_map:
            sections_map[section] = []
        sections_map[section].append(row_def)

    # Build each section as a separate table.
    tables = []
    for section_name, section_rows_def in sections_map.items():
        columns = ["Métrica"] + period_labels
        rows: list[list] = []

        for row_def in section_rows_def:
            metric_label, _, source, key, fmt = row_def

            # Data row.
            row: list = [metric_label]
            for i, p in enumerate(sorted_periods):
                p_label = period_labels[i]
                bpa_acc = bpa_by_period.get(p_label, [])
                bpp_acc = bpp_by_period.get(p_label, [])
                dre_acc = dre_by_period.get(p_label, [])
                dfc_acc = dfc_by_period.get(p_label, [])

                val = _extract_value(
                    row_def, p, bpa_acc, bpp_acc, dre_acc, dfc_acc,
                    sorted_periods, i, capex_map=capex_map)

                if fmt == "pct":
                    row.append(_fmt(val, "pct") if val is not None else "—")
                else:
                    row.append(_fmt(val, fmt) if val is not None else "—")

            rows.append(row)

        tables.append({
            "title": f"{section_name} — {label}",
            "type": "table",
            "negative_red": True,
            "positive_green": True,
            "columns": columns,
            "rows": rows,
            "sortable": False,
            "wide": True,
            "extra_class": "comprehensive",
            "column_align": ["left"] + ["right"] * n_periods,
        })

    return tables


# ── [v25] Additional indicator charts for Períodos/Séries Temporais tabs ──────

def build_indicator_charts(periods: list[dict], label: str,
    bpa_result: dict | None = None,
    bpp_result: dict | None = None,
    capex_map: dict | None = None,
) -> list[dict]:
    """[v25/v26] Build 3 additional bar charts from the Indicadores data.
    [v26] Fixed: compute ratios inline from metrics+accounts (same as
    comprehensive table), not from per-period ratios dict which doesn't
    have current_ratio/cash_ratio/debt_equity. Fixed Capital Giro. Fixed
    Dív. Bruta color. Added _fixedYWidth to all charts for alignment.
    [v2.4] Added ``capex_map`` kwarg — the CAPEX bar in the 3rd chart
    uses the real CapEx engine value (from ``capex_periods()``) when
    available, falling back to FCI proxy otherwise. Description updated
    to reflect the source.
    """
    from skills.cvm.financials.report._helpers import _CHART_COLORS, _pct_of

    def _sort_key(p):
        period = str(p.get("period") or p.get("quarter") or "")
        if "T" in period:
            try:
                q = int(period.split("T")[0])
                y = int(period.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                return (0, 0)
        try:
            return (int(period), 0)
        except ValueError:
            return (0, 0, period)

    sorted_periods = sorted(
        [p for p in periods if p.get("period") or p.get("quarter")],
        key=_sort_key,
    )
    if len(sorted_periods) < 2:
        return []

    labels = [str(p.get("period") or p.get("quarter", "")) for p in sorted_periods]

    # Build accounts lookups for each statement
    bpa_by_period = _build_accounts_by_period(bpa_result)
    bpp_by_period = _build_accounts_by_period(bpp_result)

    charts = []

    # Chart 1: Ratios — Giro Ativos, Liquidez Corrente, Liquidez Imediata, Div Br/Patrim
    giro, liq_corr, liq_imed, div_pat = [], [], [], []
    for i, p in enumerate(sorted_periods):
        m = p.get("metrics") or {}
        p_label = labels[i]
        bpa_acc = bpa_by_period.get(p_label, [])
        bpp_acc = bpp_by_period.get(p_label, [])

        # Giro Ativos = Receita / Ativo Total
        receita = _num_or_none(m.get("receita_liquida"))
        ativo = _get_account_value(bpa_acc, "1")
        if ativo is None:
            ativo = _num_or_none(m.get("ativo_total"))
        giro.append(receita / ativo if receita and ativo and ativo != 0 else None)

        # Liquidez Corrente = Ativo Circ / Passivo Circ
        ac = _get_account_value(bpa_acc, "1.01")
        pc = _get_account_value(bpp_acc, "2.01")
        liq_corr.append(ac / pc if ac and pc and pc != 0 else None)

        # Liquidez Imediata = Caixa / Passivo Circ
        caixa_acc = _get_account_value(bpa_acc, "1.01.01")
        caixa = caixa_acc if caixa_acc is not None else _num_or_none(m.get("caixa"))
        liq_imed.append(caixa / pc if caixa and pc and pc != 0 else None)

        # Div Br/Patrim = Dív. Bruta / PL
        d_circ = _get_account_value(bpp_acc, "2.01.04")
        d_ncirc = _get_account_value(bpp_acc, "2.02.01")
        db = (d_circ or 0) + (d_ncirc or 0) if (d_circ is not None or d_ncirc is not None) else _num_or_none(m.get("divida_bruta"))
        pl_acc = _get_account_value(bpp_acc, "2.03")
        pl = pl_acc if pl_acc is not None else _num_or_none(m.get("patrimonio_liquido"))
        div_pat.append(db / pl if db and pl and pl != 0 else None)

    if any(v is not None for v in giro + liq_corr + liq_imed + div_pat):
        charts.append({
            "type": "chart",
            "title": f"Indicadores de Liquidez e Alavancagem — {label}",
            "description": "Giro Ativos, Liquidez Corrente, Liquidez Imediata e Dív. Bruta/Patrimônio por período.",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {"label": "Giro Ativos", "data": giro,
                         "backgroundColor": "#1e3a5f", "borderColor": "#1e3a5f"},
                        {"label": "Liquidez Corrente", "data": liq_corr,
                         "backgroundColor": "#7c3aed", "borderColor": "#7c3aed"},
                        {"label": "Liquidez Imediata", "data": liq_imed,
                         "backgroundColor": "#c4b5fd", "borderColor": "#c4b5fd"},
                        {"label": "Div Br / Patrim", "data": div_pat,
                         "backgroundColor": "#6b21a8", "borderColor": "#6b21a8"},
                    ],
                },
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "_fixedYWidth": 90,
                    "scales": {"y": {"ticks": {},
                                     "title": {"display": True, "text": "Ratio"}}},
                    "plugins": {"title": {"display": True, "text": "Liquidez e Alavancagem"}},
                },
            },
        })

    # Chart 2: BRL — Disponibilidades, Dív. Bruta, Dív. Líquida, Capital Giro (in millions)
    dispo, div_bruta, div_liq, cap_giro = [], [], [], []
    for i, p in enumerate(sorted_periods):
        m = p.get("metrics") or {}
        p_label = labels[i]
        bpa_acc = bpa_by_period.get(p_label, [])
        bpp_acc = bpp_by_period.get(p_label, [])

        # Disponibilidades = Caixa (from accounts or metrics)
        caixa_acc = _get_account_value(bpa_acc, "1.01.01")
        caixa = caixa_acc if caixa_acc is not None else _num_or_none(m.get("caixa"))
        dispo.append(caixa / 1_000_000 if caixa is not None else None)

        # Dív. Bruta from accounts or metrics
        d_circ = _get_account_value(bpp_acc, "2.01.04")
        d_ncirc = _get_account_value(bpp_acc, "2.02.01")
        db = (d_circ or 0) + (d_ncirc or 0) if (d_circ is not None or d_ncirc is not None) else _num_or_none(m.get("divida_bruta"))
        div_bruta.append(db / 1_000_000 if db is not None else None)

        # Dív. Líquida = Dív. Bruta - Caixa
        if db is not None and caixa is not None:
            div_liq.append((db - caixa) / 1_000_000)
        else:
            div_liq.append(None)

        # Capital Giro = Ativo Circ - Passivo Circ
        ac = _get_account_value(bpa_acc, "1.01")
        pc = _get_account_value(bpp_acc, "2.01")
        if ac is not None and pc is not None:
            cap_giro.append((ac - pc) / 1_000_000)
        else:
            cap_giro.append(None)

    if any(v is not None for v in dispo + div_bruta + div_liq + cap_giro):
        charts.append({
            "type": "chart",
            "title": f"Disponibilidades e Endividamento — {label}",
            "description": "Disponibilidades, Dív. Bruta, Dív. Líquida e Capital de Giro por período (R$ milhões).",
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {"label": "Disponibilidades", "data": dispo,
                         "backgroundColor": "#78350f", "borderColor": "#78350f"},
                        {"label": "Dív. Bruta", "data": div_bruta,
                         "backgroundColor": "#b91c1c", "borderColor": "#b91c1c"},
                        {"label": "Dív. Líquida", "data": div_liq,
                         "backgroundColor": "#ea580c", "borderColor": "#ea580c"},
                        {"label": "Capital Giro", "data": cap_giro,
                         "backgroundColor": "#facc15", "borderColor": "#facc15"},
                    ],
                },
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "_fixedYWidth": 90, "_absMillions": True,
                    "scales": {"y": {"ticks": {},
                                     "title": {"display": True, "text": "R$ (mi)"}}},
                    "plugins": {"title": {"display": True, "text": "Disponibilidades e Endividamento"}},
                },
            },
        })

    # Chart 3: BRL — EBIT, EBITDA, CAPEX (in millions)
    # [v2.4] CAPEX now uses the real capex_at engine when capex_map is
    # provided (description-search: imobilizado/intangivel, scoped to
    # DFC 6.02.%, TTM-derived from DFP + ITR). Falls back to FCI proxy
    # (total investing cash flow) when the engine returns None.
    ebit_vals, ebitda_vals, capex_vals = [], [], []
    capex_engine_used = False
    for p in sorted_periods:
        m = p.get("metrics") or {}
        e = _num_or_none(m.get("ebit"))
        ebit_vals.append(e / 1_000_000 if e is not None else None)
        ed = _num_or_none(m.get("ebitda"))
        ebitda_vals.append(ed / 1_000_000 if ed is not None else None)
        # [v2.4] CapEx: try the real engine first, fall back to FCI.
        # [v2 fix] Compute data_fim_exerc from year+quarter when missing
        # (quarterly mode periods have year+quarter but no data_fim_exerc).
        cx = None
        if capex_map:
            period_label = str(p.get("period") or p.get("quarter") or "")
            date_label = str(p.get("data_fim_exerc") or "")
            year_label = str(p.get("year") or "")
            if not date_label and year_label:
                quarter_num = p.get("quarter")
                if quarter_num is not None:
                    month_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
                    try:
                        me = month_end.get(int(quarter_num))
                    except (TypeError, ValueError):
                        me = None
                    if me:
                        date_label = f"{year_label}-{me}"
            year_from_date = date_label[:4] if len(date_label) >= 4 else ""
            for lookup_key in (date_label, period_label, year_label, year_from_date):
                if lookup_key and lookup_key in capex_map:
                    v = capex_map[lookup_key]
                    if v is not None:
                        cx = abs(_num_or_none(v))
                        capex_engine_used = True
                        break
        if cx is None:
            cx = _num_or_none(m.get("fci"))
        capex_vals.append(cx / 1_000_000 if cx is not None else None)

    if any(v is not None for v in ebit_vals + ebitda_vals + capex_vals):
        capex_desc = (
            "EBIT, EBITDA e CAPEX (engine: imobilizado/intangivel) por período (R$ milhões)."
            if capex_engine_used else
            "EBIT, EBITDA e CAPEX (FCI proxy) por período (R$ milhões)."
        )
        charts.append({
            "type": "chart",
            "title": f"EBIT, EBITDA e CAPEX — {label}",
            "description": capex_desc,
            "chart_data": {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {"label": "EBIT", "data": ebit_vals,
                         "backgroundColor": "#60a5fa", "borderColor": "#60a5fa"},
                        {"label": "EBITDA", "data": ebitda_vals,
                         "backgroundColor": "#c4b5fd", "borderColor": "#c4b5fd"},
                        {"label": "CAPEX", "data": capex_vals,
                         "backgroundColor": "#1e3a5f", "borderColor": "#1e3a5f"},
                    ],
                },
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "_fixedYWidth": 90, "_absMillions": True,
                    "scales": {"y": {"ticks": {},
                                     "title": {"display": True, "text": "R$ (mi)"}}},
                    "plugins": {"title": {"display": True, "text": "EBIT, EBITDA e CAPEX"}},
                },
            },
        })

    return charts