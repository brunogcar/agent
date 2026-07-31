"""Mode: bpa -- Balanço Patrimonial Ativo (Balance Sheet — Assets).

Queries DFP (annual) + ITR (quarterly cumulative) BPA for the last N periods.
Returns the full BPA assets statement matching the CVM chart of accounts:

  1       = Ativo Total (Total Assets)
  1.01    = Ativo Circulante (Current Assets) — OLD chart
            / Caixa e Equivalentes — NEW chart (chart drift over years)
  1.01.01 = Caixa e Equivalentes (Cash & Equivalents)
  1.01.02 = Aplicações Financeiras (Short-term Investments)
  1.01.03 = Contas a Receber (Receivables)
  1.01.04 = Estoques (Inventories)
  1.02    = Ativo Não Circulante (Non-current Assets) — OLD chart
            / Aplicações Financeiras — NEW chart
  1.02.01 = Ativo Não Circulante (sub — Non-current Assets sub-line)
  1.02.03 = Imobilizado (Property, Plant & Equipment) — OLD chart
  1.02.04 = Intangível (Intangibles) — OLD chart
  1.03-1.08 = newer chart sub-lines (varies per filer; multiple descriptions
              per code — CVM chart has changed over the years)

[v1.9] BPA is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the DVA + DRE +
quarterly modes handle BPP/DRE/DFC.

⚠️ Multiple labels per code (CVM chart drift):
  The BPA chart has CHANGED over the years. Older filers use:
    1.01 = Ativo Circulante, 1.02 = Ativo Não Circulante,
    1.02.03 = Imobilizado, 1.02.04 = Intangível
  Newer filers use:
    1.01 = Caixa e Equivalentes, 1.02 = Aplicações Financeiras,
    1.07 = Imobilizado, 1.08 = Intangível
  Codes 1.01-1.08 exist in BOTH charts but have DIFFERENT meanings. The
  engines query by codigo only (no grupo filter needed — codes 1.xx are
  unique to BPA). This is a data correctness issue, not a code bug — the
  engines return whatever 1.01 is for that filer.

BPA vs BPP distinction:
  - grupo LIKE '%Patrimonial Ativo%'  = BPA (this mode — assets side)
  - grupo LIKE '%Patrimonial Passivo%' = BPP (DIFFERENT statement —
    liabilities + equity side; NOT queried here)

Registered as "bpa" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode


# ── BPA account codes + labels ───────────────────────────────────────────────

_BPA_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP BPA uses 1.xx codes. Verified against real DFP data:
    # 1 (Ativo Total) has 6685 rows; 1.01 has 6685 rows (multiple descriptions
    # — CVM chart changed over years); 1.01.01 has 6536 rows; 1.02.03 has 6505
    # rows; 1.02.04 has 6430 rows. Codes 1.01-1.08 are unique to BPA.
    #
    # Note on multiple labels per code (CVM chart drift over years):
    #   1.01 — OLD: "Ativo Circulante" / NEW: "Caixa e Equivalentes"
    #   1.02 — OLD: "Ativo Não Circulante" / NEW: "Aplicações Financeiras"
    #   1.02.03 — OLD: "Imobilizado" (NEW chart uses 1.07 instead)
    #   1.02.04 — OLD: "Intangível" (NEW chart uses 1.08 instead)
    #   1.03 — multiple: "Empréstimos e Recebíveis" / "Tributos Diferidos"
    #   1.04 — multiple: "Tributos Diferidos" / "Outros Ativos"
    #   1.05 — multiple: "Outros Ativos" / "Investimentos"
    #   1.06 — multiple: "Investimentos" / "Imobilizado"
    #   1.07 — NEW chart: "Imobilizado" (replaces 1.02.03)
    #   1.08 — NEW chart: "Intangível" (replaces 1.02.04)
    ("1",       "Ativo Total",                              "total"),
    ("1.01",    "Ativo Circulante",                         "current"),
    ("1.01.01", "Caixa e Equivalentes",                     "cash"),
    ("1.01.02", "Aplicações Financeiras",                   "investments_short"),
    ("1.01.03", "Contas a Receber",                         "receivables"),
    ("1.01.04", "Estoques",                                 "inventory"),
    ("1.02",    "Ativo Não Circulante",                     "non_current"),
    ("1.02.01", "Ativo Não Circulante (sub)",               "non_current_sub"),
    ("1.02.03", "Imobilizado",                              "ppe"),
    ("1.02.04", "Intangível",                               "intangibles"),
    ("1.03",    "Empréstimos e Recebíveis / Tributos",      "other_1"),
    ("1.04",    "Tributos Diferidos / Outros Ativos",       "other_2"),
    ("1.05",    "Outros Ativos / Investimentos",            "other_3"),
    ("1.06",    "Investimentos / Imobilizado",              "other_4"),
    ("1.07",    "Imobilizado (novo formato)",               "ppe_new"),
    ("1.08",    "Intangível (novo formato)",                "intangibles_new"),
]


@register_mode(
    "bpa",
    description=(
        "Balanço Patrimonial Ativo (BPA) — Balance Sheet (Assets side). "
        "Returns the full BPA for the last N periods (annual or quarterly), "
        "structured top-to-bottom (Ativo Total → Circulante → Caixa → "
        "Aplicações → Contas a Receber → Estoques → Não Circulante → "
        "Imobilizado → Intangível). BPA is available in both DFP (annual) "
        "and ITR (quarterly cumulative). Filters by grupo "
        "'%Patrimonial Ativo%' (NOT '%Patrimonial Passivo%' — that is the "
        "separate BPP statement). Codes 1.xx are unique to BPA so no grupo "
        "filter is strictly needed, but the LIKE filter future-proofs "
        "against CVM adding overlapping codes."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="bpa", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="bpa", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="bpa", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def bpa(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Balanço Patrimonial Ativo (BPA) for the last N periods.

    Args:
        company: B3 ticker, name fragment, or CNPJ. Required.
        periods: Number of periods to return. Default: 5.
        consolidado: 1=consolidated (default), 0=individual.
        quarterly: 1=quarterly (ITR meses=3/6/9 + DFP meses=12),
                   0=annual only (DFP meses=12). Default: 0.

    Returns:
        Dict with:
          - status: "ok" or "not_found" / "error"
          - company: resolved company name
          - period_type: "annual" or "quarterly"
          - periods: list of {data_fim_exerc, meses, accounts: {codigo: {label, section, valor_brl}}}
            sorted newest-first.
          - If the company has no BPA data, returns status="not_found".
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
    from data_sources.cvm._bridge import resolve_company

    codes = [c[0] for c in _BPA_CODES]
    code_ph = ",".join("?" * len(codes))
    label_map = {c[0]: c[1] for c in _BPA_CODES}
    section_map = {c[0]: c[2] for c in _BPA_CODES}

    # grupo filter: BPA only (assets side). Excludes "Patrimonial Passivo"
    # (BPP — liabilities + equity side) which is a different statement.
    GRUPO_FILTER = "%Patrimonial Ativo%"

    # ── Helper: fetch BPA rows from a connection ──────────────────────────
    def _fetch_bpa_rows(conn, empresa_ids, target_dates, consol):
        emp_ph = ",".join("?" * len(empresa_ids))
        date_ph = ",".join("?" * len(target_dates))
        return conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, meses, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND consolidado=?
                AND grupo LIKE ?
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, consol, GRUPO_FILTER, *target_dates),
        ).fetchall()

    def _build_periods_data(rows):
        periods_data: dict[str, dict] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = {"meses": r["meses"], "accounts": {}}
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key]["accounts"][r["codigo"]] = {
                "label": label_map.get(r["codigo"], r["descricao"]),
                "section": section_map.get(r["codigo"], "unknown"),
                "valor_brl": valor_brl,
            }
        return periods_data

    # ── Annual mode (DFP only) ────────────────────────────────────────────
    if not quarterly:
        conn = connect_dfp(read_only=True)
        try:
            empresa_ids, company_name = resolve_company(conn, company)
            if not empresa_ids:
                return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

            emp_ph = ",".join("?" * len(empresa_ids))

            year_rows = conn.execute(
                f"""SELECT DISTINCT data_fim_exerc FROM contas
                    WHERE id_empresa IN ({emp_ph})
                    AND codigo IN ({code_ph})
                    AND meses=12 AND consolidado=?
                    AND grupo LIKE ?
                    ORDER BY data_fim_exerc DESC LIMIT ?""",
                (*empresa_ids, *codes, consolidado, GRUPO_FILTER, periods),
            ).fetchall()

            if not year_rows:
                return {"status": "not_found",
                        "error": f"No BPA data found for '{company}'"}

            target_dates = [r["data_fim_exerc"] for r in year_rows]
            rows = _fetch_bpa_rows(conn, empresa_ids, target_dates, consolidado)
            periods_data = _build_periods_data(rows)

            return {
                "status": "ok",
                "company": company_name,
                "period_type": "annual",
                "periods": [
                    {"data_fim_exerc": date, "meses": periods_data[date]["meses"],
                     "accounts": periods_data[date]["accounts"]}
                    for date in sorted(periods_data.keys(), reverse=True)
                ],
            }
        except FileNotFoundError as e:
            return {"status": "not_synced", "error": str(e)}
        finally:
            conn.close()

    # ── Quarterly mode (ITR + DFP) ────────────────────────────────────────
    # ITR has meses=3/6/9 (cumulative), DFP has meses=12 (annual).
    # We fetch all periods sorted by date DESC, LIMIT periods.
    dfp_conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(dfp_conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        emp_ph = ",".join("?" * len(empresa_ids))

        # Get DFP annual BPA dates
        dfp_dates = dfp_conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND grupo LIKE ?
                ORDER BY data_fim_exerc DESC""",
            (*empresa_ids, *codes, consolidado, GRUPO_FILTER),
        ).fetchall()
        dfp_date_list = [r["data_fim_exerc"] for r in dfp_dates]
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        dfp_conn.close()

    # Get ITR quarterly BPA dates
    itr_date_list = []
    try:
        itr_conn = connect_itr(read_only=True)
        try:
            itr_empresa_ids, _ = resolve_company(itr_conn, company)
            if itr_empresa_ids:
                itr_emp_ph = ",".join("?" * len(itr_empresa_ids))
                itr_dates = itr_conn.execute(
                    f"""SELECT DISTINCT data_fim_exerc FROM contas
                        WHERE id_empresa IN ({itr_emp_ph})
                        AND codigo IN ({code_ph})
                        AND meses IN (3, 6, 9) AND consolidado=?
                        AND grupo LIKE ?
                        ORDER BY data_fim_exerc DESC""",
                    (*itr_empresa_ids, *codes, consolidado, GRUPO_FILTER),
                ).fetchall()
                itr_date_list = [r["data_fim_exerc"] for r in itr_dates]
        finally:
            itr_conn.close()
    except FileNotFoundError:
        pass  # ITR not synced — return annual only

    # Merge + deduplicate dates (ITR Q4 = DFP annual, same date)
    all_dates = sorted(set(dfp_date_list + itr_date_list), reverse=True)[:periods]

    if not all_dates:
        return {"status": "not_found",
                "error": f"No BPA data found for '{company}'"}

    # Fetch rows from both DBs
    all_rows = []

    # DFP rows
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_rows = _fetch_bpa_rows(dfp_conn, empresa_ids, all_dates, consolidado)
        all_rows.extend(dfp_rows)
    finally:
        dfp_conn.close()

    # ITR rows (if any ITR dates exist in all_dates)
    itr_dates_in_range = [d for d in all_dates if d in itr_date_list and d not in dfp_date_list]
    if itr_dates_in_range:
        try:
            itr_conn = connect_itr(read_only=True)
            try:
                itr_empresa_ids, _ = resolve_company(itr_conn, company)
                if itr_empresa_ids:
                    itr_rows = _fetch_bpa_rows(itr_conn, itr_empresa_ids, itr_dates_in_range, consolidado)
                    all_rows.extend(itr_rows)
            finally:
                itr_conn.close()
        except FileNotFoundError:
            pass

    periods_data = _build_periods_data(all_rows)

    return {
        "status": "ok",
        "company": company_name,
        "period_type": "quarterly",
        "periods": [
            {"data_fim_exerc": date, "meses": periods_data[date]["meses"],
             "accounts": periods_data[date]["accounts"]}
            for date in sorted(periods_data.keys(), reverse=True)
            if date in periods_data
        ],
    }
