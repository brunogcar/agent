"""Mode: bpp -- Balanço Patrimonial Passivo (Balance Sheet — Liabilities + Equity).

Queries DFP (annual) + ITR (quarterly cumulative) BPP for the last N periods.
Returns the full BPP liabilities + equity statement matching the CVM chart of
accounts:

  2       = Passivo Total (Total Liabilities + Equity)
  2.01    = Passivo Circulante (Current Liabilities) — OLD chart
            / Passivos Financeiros para Negociação — NEW chart (chart drift)
  2.01.01 = Fornecedores / Obrigações Sociais / Contas a Pagar (MULTIPLE labels
            per code — CVM chart drift; 6476 rows; "Obrigações Sociais e
            Trabalhistas" is most common at 6317 rows)
  2.01.04 = Empréstimos e Financiamentos Circulante (Short-term Debt)
  2.02    = Passivo Não Circulante (Non-current Liabilities) — OLD chart
            / Outros Passivos Financeiros — NEW chart
  2.02.01 = Empréstimos e Financiamentos Não Circulante (Long-term Debt)
  2.03    = Patrimônio Líquido Consolidado (Equity) — OLD chart
            / Passivos Financeiros ao Custo Amortizado (DEBT!) — NEW chart
            6352/6681 rows (95%) still use the OLD chart (PL), so the pl
            engine works for the majority. This is a DATA correctness issue,
            not a code bug — documented as such.
  2.03.01 = Capital Social (Share Capital)
  2.03.02 = Reservas de Capital (Capital Reserves)
  2.03.04 = Reservas de Lucros (Profit Reserves)
  2.03.05 = Lucros Acumulados (Retained Earnings)
  2.03.09 = Participação Não Controladores (Non-controlling Interest)
  2.04-2.08 = newer chart sub-lines (varies per filer; the NEW chart moves
              PL to 2.08 and uses 2.03 for amortized-cost debt instead)

[v1.10] BPP is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the BPA + DRE +
DVA + quarterly modes handle BPA/BPP/DRE/DFC/DVA.

⚠️ The 2.03 meaning trap (OLD vs NEW chart):
  The BPP chart has CHANGED over the years. Older filers use:
    2.03 = Patrimônio Líquido Consolidado (PL)
  Newer filers use:
    2.03 = Passivos Financeiros ao Custo Amortizado (DEBT — not PL!)
    2.08 = Patrimônio Líquido Consolidado (PL moves here in the new chart)
  The pl engine queries 2.03 and gets whatever the filer uses. 95% of filers
  (6352/6681 rows) still use the OLD chart (PL), so the engine works for the
  majority. This is a data correctness issue, not a code bug — callers needing
  precise semantics should filter by `descricao` as well, or check whether
  2.08 exists (only present in the NEW chart).

⚠️ Multiple labels per code 2.01.01:
  Code 2.01.01 (6476 rows) has MULTIPLE descriptions across filers:
    - "Obrigações Sociais e Trabalhistas" (6317 rows — most common)
    - "Fornecedores"
    - "Contas a Pagar"
    - "Depósitos"
  The payables engine uses 2.01.01 and gets whatever the filer uses. Same
  pattern as BPA's 1.01 multiple-labels-per-code — documented in BPP.md.

BPP vs BPA distinction:
  - grupo LIKE '%Patrimonial Passivo%' = BPP (this mode — liabilities + equity)
  - grupo LIKE '%Patrimonial Ativo%'   = BPA (DIFFERENT statement — assets
    side; NOT queried here)

Registered as "bpp" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode


# ── BPP account codes + labels ───────────────────────────────────────────────

_BPP_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP BPP uses 2.xx codes. Verified against real DFP data:
    # 2 (Passivo Total) has 6681 rows; 2.01 has 6681 rows (multiple descriptions
    # — CVM chart changed over years); 2.01.01 has 6476 rows (MULTIPLE
    # descriptions — "Obrigações Sociais e Trabalhistas" is most common at 6317
    # rows; "Fornecedores", "Contas a Pagar", "Depósitos" also appear);
    # 2.01.04 has 6363 rows; 2.02 has 6681 rows; 2.02.01 has 6507 rows;
    # 2.03 has 6681 rows (6352 rows say "Patrimônio Líquido" — OLD chart;
    # newer filers say "Passivos Financeiros ao Custo Amortizado" — NEW chart);
    # 2.03.01 has 6579 rows; 2.03.02 has 6558 rows; 2.03.04 has 6480 rows;
    # 2.03.05 has 6453 rows; 2.03.09 has 6355 rows.
    # Codes 2.xx are unique to BPP — no grupo filter needed strictly.
    #
    # Note on the 2.03 meaning trap (CVM chart drift over years):
    #   2.03 — OLD chart: "Patrimônio Líquido" (PL)
    #          NEW chart: "Passivos Financeiros ao Custo Amortizado" (DEBT!)
    #          95% of filers (6352/6681 rows) still use OLD chart.
    #   2.08 — NEW chart only: "Patrimônio Líquido Consolidado" (PL moves here)
    #   2.01.01 — MULTIPLE descriptions across filers (6317 rows "Obrigações
    #             Sociais e Trabalhistas" most common; "Fornecedores" / "Contas
    #             a Pagar" / "Depósitos" also appear)
    ("2",       "Passivo Total",                              "total"),
    ("2.01",    "Passivo Circulante",                         "current"),
    ("2.01.01", "Fornecedores / Obrigações",                  "payables"),
    ("2.01.04", "Empréstimos e Financiamentos (Circulante)",  "debt_short"),
    ("2.02",    "Passivo Não Circulante",                     "non_current"),
    ("2.02.01", "Empréstimos e Financiamentos (Não Circ.)",   "debt_long"),
    ("2.03",    "Patrimônio Líquido",                         "equity"),
    ("2.03.01", "Capital Social",                             "capital"),
    ("2.03.02", "Reservas de Capital",                        "reserves_capital"),
    ("2.03.04", "Reservas de Lucros",                         "reserves_profit"),
    ("2.03.05", "Lucros Acumulados",                          "retained_earnings"),
    ("2.03.09", "Participação Não Controladores",              "minority"),
    # New chart codes (2.04-2.08) — included for completeness.
    # 2.04-2.07 exist only in the NEW chart. 2.08 is the NEW chart's location
    # for Patrimônio Líquido (replaces 2.03 which becomes amortized-cost debt
    # in the NEW chart). Old-chart filers don't populate these rows.
    ("2.04",    "Provisões (novo formato)",                   "provisions_new"),
    ("2.05",    "Passivos Fiscais (novo formato)",             "tax_liabilities_new"),
    ("2.06",    "Outros Passivos (novo formato)",              "other_liabilities_new"),
    ("2.07",    "Passivos s/ Ativos Não Correntes (novo)",     "non_current_new"),
    ("2.08",    "Patrimônio Líquido (novo formato)",           "equity_new"),
]


@register_mode(
    "bpp",
    description=(
        "Balanço Patrimonial Passivo (BPP) — Balance Sheet (Liabilities + "
        "Equity side). Returns the full BPP for the last N periods (annual or "
        "quarterly), structured top-to-bottom (Passivo Total → Circulante → "
        "Fornecedores → Empréstimos Circulante → Não Circulante → Empréstimos "
        "Não Circulante → Patrimônio Líquido → Capital Social → Reservas → "
        "Lucros Acumulados → Participação Não Controladores). BPP is available "
        "in both DFP (annual) and ITR (quarterly cumulative). Filters by grupo "
        "'%Patrimonial Passivo%' (NOT '%Patrimonial Ativo%' — that is the "
        "separate BPA statement). Codes 2.xx are unique to BPP so no grupo "
        "filter is strictly needed, but the LIKE filter future-proofs against "
        "CVM adding overlapping codes."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="bpp", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="bpp", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="bpp", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def bpp(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Balanço Patrimonial Passivo (BPP) for the last N periods.

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
          - If the company has no BPP data, returns status="not_found".
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
    from data_sources.cvm._bridge import resolve_company

    codes = [c[0] for c in _BPP_CODES]
    code_ph = ",".join("?" * len(codes))
    label_map = {c[0]: c[1] for c in _BPP_CODES}
    section_map = {c[0]: c[2] for c in _BPP_CODES}

    # grupo filter: BPP only (liabilities + equity side). Excludes
    # "Patrimonial Ativo" (BPA — assets side) which is a different statement.
    GRUPO_FILTER = "%Patrimonial Passivo%"

    # ── Helper: fetch BPP rows from a connection ──────────────────────────
    def _fetch_bpp_rows(conn, empresa_ids, target_dates, consol):
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
                        "error": f"No BPP data found for '{company}'"}

            target_dates = [r["data_fim_exerc"] for r in year_rows]
            rows = _fetch_bpp_rows(conn, empresa_ids, target_dates, consolidado)
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

        # Get DFP annual BPP dates
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

    # Get ITR quarterly BPP dates
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
                "error": f"No BPP data found for '{company}'"}

    # Fetch rows from both DBs
    all_rows = []

    # DFP rows
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_rows = _fetch_bpp_rows(dfp_conn, empresa_ids, all_dates, consolidado)
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
                    itr_rows = _fetch_bpp_rows(itr_conn, itr_empresa_ids, itr_dates_in_range, consolidado)
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
