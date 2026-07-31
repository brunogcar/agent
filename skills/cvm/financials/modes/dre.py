"""Mode: dre -- Demonstração do Resultado do Exercício (Income Statement).

Queries DFP (annual) + ITR (quarterly cumulative) DRE for the last N periods.
Returns the full DRE statement matching the CVM chart of accounts:

  3.01 = Receita Líquida (Revenue)
  3.02 = Custo dos Bens e Serviços Vendidos (COGS)
  3.03 = Resultado Bruto (Gross Profit)
  3.04 = Despesas Operacionais (Operating Expenses)
  3.05 = Resultado Antes dos Tributos sobre o Lucro (EBIT)
  3.06 = Resultado Financeiro (Financial Result)
  3.07 = Resultado Líquido das Operações Continuadas (Net Continuing Ops)
  3.08 = Imposto de Renda e Contribuição Social (Income Tax)
  3.09 = Lucro/Prejuízo Consolidado do Período (Net Income)
  3.11 = Lucro/Prejuízo Consolidado do Período (alt — some filers use this)

[v1.8] DRE is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the DVA + quarterly
modes handle BPA/BPP/DRE/DFC.

DRE vs DRA distinction:
  - grupo LIKE '%Demonstração do Resultado%'       = DRE (this mode)
  - grupo LIKE '%Demonstração de Resultado Abrangente%' = DRA (DIFFERENT
    statement — comprehensive income; NOT queried here)

Registered as "dre" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode


# ── DRE account codes + labels ───────────────────────────────────────────────

_DRE_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP DRE uses 3.xx codes. Verified against real DFP data:
    # 3.01-3.09 each have ~6628-6629 rows; 3.11 has 6377 rows (some filers
    # use 3.09 or 3.13 instead).
    #
    # Note on multiple labels per code (CVM chart changed over years):
    #   3.01 — some filers use "Receitas da Intermediação Financeira" (banks)
    #   3.03 — some filers use "Resultado Bruto Intermediação Financeira"
    #   3.05 — also labeled "Resultado Antes dos Tributos sobre o Lucro"
    #   3.06 — ALSO labeled "Imposto de Renda" by some filers (chart drift)
    #   3.07 — NOT in SUMMARY_CODES prior to v1.8 (added this version)
    #   3.08 — ALSO labeled "Operações Descontinuadas" by some filers
    #   3.09 — currently in SUMMARY_CODES as "Resultado Líquido (Continuadas)"
    #   3.11 — some filers use 3.09 or 3.13 instead (6377 vs 6629 rows)
    ("3.01",  "Receita Líquida de Vendas e/ou Serviços",                "revenue"),
    ("3.02",  "Custo dos Bens e/ou Serviços Vendidos",                  "costs"),
    ("3.03",  "Resultado Bruto",                                        "gross_profit"),
    ("3.04",  "Despesas Administrativas, Gerais e Comerciais",          "operating_expenses"),
    ("3.05",  "Resultado Antes do Resultado Financeiro e dos Tributos", "ebit"),
    ("3.06",  "Resultado Financeiro",                                   "financial_result"),
    ("3.07",  "Resultado Líquido das Operações Continuadas",            "net_continuing"),
    ("3.08",  "Imposto de Renda e Contribuição Social sobre o Lucro",   "tax"),
    ("3.09",  "Lucro/Prejuízo Consolidado do Período",                  "net_income"),
    ("3.11",  "Lucro/Prejuízo Consolidado do Período (alt)",            "net_income_alt"),
]


@register_mode(
    "dre",
    description=(
        "Demonstração do Resultado do Exercício (DRE) — Income Statement. "
        "Returns the full DRE for the last N periods (annual or quarterly), "
        "structured top-to-bottom (Receita → Custos → Lucro Bruto → "
        "Despesas Operacionais → EBIT → Resultado Financeiro → Imposto de "
        "Renda → Lucro Líquido). DRE is available in both DFP (annual) and "
        "ITR (quarterly cumulative). Filters by grupo "
        "'%Demonstração do Resultado%' (NOT '%Resultado Abrangente%' — that "
        "is the separate DRA statement)."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dre", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def dre(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Demonstração do Resultado do Exercício (DRE) for the last N periods.

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
          - If the company has no DRE data, returns status="not_found".
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
    from data_sources.cvm._bridge import resolve_company

    codes = [c[0] for c in _DRE_CODES]
    code_ph = ",".join("?" * len(codes))
    label_map = {c[0]: c[1] for c in _DRE_CODES}
    section_map = {c[0]: c[2] for c in _DRE_CODES}

    # grupo filter: DRE only. Excludes "Demonstração de Resultado Abrangente"
    # (DRA) which is a different statement.
    GRUPO_FILTER = "%Demonstração do Resultado%"

    # ── Helper: fetch DRE rows from a connection ──────────────────────────
    def _fetch_dre_rows(conn, empresa_ids, target_dates, consol):
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
                        "error": f"No DRE data found for '{company}'"}

            target_dates = [r["data_fim_exerc"] for r in year_rows]
            rows = _fetch_dre_rows(conn, empresa_ids, target_dates, consolidado)
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

        # Get DFP annual DRE dates
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

    # Get ITR quarterly DRE dates
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
                "error": f"No DRE data found for '{company}'"}

    # Fetch rows from both DBs
    all_rows = []

    # DFP rows
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_rows = _fetch_dre_rows(dfp_conn, empresa_ids, all_dates, consolidado)
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
                    itr_rows = _fetch_dre_rows(itr_conn, itr_empresa_ids, itr_dates_in_range, consolidado)
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
