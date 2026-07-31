"""Mode: dva -- Demonstração do Valor Adicionado (Value Added Statement).

Queries DFP (annual) + ITR (quarterly cumulative) DVA for the last N periods.
Returns the full DVA statement structured in 2 sections matching the CVM chart
of accounts + the private spreadsheet:

  Generation side (how wealth is created):
    1   = Receitas (Revenues)
    2   = Insumos (Inputs acquired from third parties)
    3   = Valor Adicionado Bruto (Gross Value Added)
    4   = Retenções (Retentions)
    5   = Valor Adicionado Líquido (Net Value Added produced)
    5.1 = Depreciação, Amortização e Baixas
    6   = Valor Adicionado Recebido em Transferência (VA Received)
    7   = Valor Adicionado Total a Distribuir (Total VA to Distribute)

  Distribution side (how wealth is distributed):
    8.1 = Pessoal (Personnel)
    8.2 = Impostos, Taxas e Contribuições (Government / Taxes)
    8.3 = Remuneração de Capital de Terceiros (Lenders / Interest)
    8.4 = Remuneração de Capital Próprio (Shareholders)

[v1.7] DVA is available in BOTH DFP (annual, meses=12) and ITR (quarterly
cumulative, meses=3/6/9). This mode queries both databases — DFP for annual
periods and ITR+DFP for quarterly periods — matching how the quarterly mode
handles BPA/BPP/DRE/DFC.

Registered as "dva" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode


# ── DVA account codes + labels ───────────────────────────────────────────────

_DVA_CODES: list[tuple[str, str, str]] = [
    # (codigo, label, section)
    # CVM DFP DVA uses 7.xx codes (NOT 1-8). Verified against real DFP data:
    # 7.08.xx is the dominant format (16808 rows for 7.08.04); 7.11.xx is a
    # newer format used by ~75 rows only. We query both.
    #
    # Generation side (how wealth is created):
    ("7.01",  "Receitas",                                            "generation"),
    ("7.03",  "Insumos Adquiridos de Terceiros",                     "generation"),
    ("7.04",  "Valor Adicionado Bruto",                              "generation"),
    ("7.05",  "Retenções",                                           "generation"),
    ("7.06",  "Valor Adicionado Líquido Produzido",                  "generation"),
    ("7.07",  "Vlr Adicionado Recebido em Transferência",            "generation"),
    ("7.08",  "Valor Adicionado Total a Distribuir",                 "generation"),
    ("7.10",  "Valor Adicionado Total a Distribuir (alt)",           "generation"),
    # Distribution side (how wealth is distributed) — old format (7.08.xx):
    ("7.08.01", "Pessoal",                                           "distribution"),
    ("7.08.02", "Impostos, Taxas e Contribuições",                   "distribution"),
    ("7.08.03", "Remuneração de Capital de Terceiros",               "distribution"),
    ("7.08.04", "Remuneração de Capital Próprio",                    "distribution"),
    # Distribution side — new format (7.11.xx, used by ~75 rows):
    ("7.11.01", "Pessoal (novo formato)",                            "distribution"),
    ("7.11.02", "Impostos, Taxas e Contribuições (novo formato)",    "distribution"),
    ("7.11.03", "Remuneração de Capital de Terceiros (novo)",        "distribution"),
    ("7.11.04", "Remuneração de Capital Próprio (novo)",             "distribution"),
]


@register_mode(
    "dva",
    description=(
        "Demonstração do Valor Adicionado (DVA) — Value Added Statement. "
        "Returns the full DVA for the last N periods (annual or quarterly), "
        "structured in generation side (codes 1-7) + distribution side "
        "(codes 8.1-8.4). Shows how the company creates and distributes "
        "wealth across stakeholders (personnel, government, lenders, "
        "shareholders). DVA is available in both DFP (annual) and ITR "
        "(quarterly cumulative)."
    ),
    params={
        "company":     "str. Required.",
        "periods":     "int. Number of periods to return. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
        "quarterly":   "int. 1=quarterly (ITR+DFP), 0=annual only (DFP). Default: 0.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"VALE3","periods":3}\')',
        'skill(domain="cvm", sub_domain="financials", mode="dva", params=\'{"company":"PETR4","quarterly":1,"periods":8}\')',
    ],
)
def dva(company: str = "", periods: int = 5, consolidado: int = 1,
        quarterly: int = 0) -> dict:
    """Demonstração do Valor Adicionado (DVA) for the last N periods.

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
          - If the company has no DVA data, returns status="not_found".
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, connect_itr, parse_escala
    from data_sources.cvm._bridge import resolve_company

    codes = [c[0] for c in _DVA_CODES]
    code_ph = ",".join("?" * len(codes))
    label_map = {c[0]: c[1] for c in _DVA_CODES}
    section_map = {c[0]: c[2] for c in _DVA_CODES}

    # ── Helper: fetch DVA rows from a connection ──────────────────────────
    def _fetch_dva_rows(conn, empresa_ids, target_dates, consol):
        emp_ph = ",".join("?" * len(empresa_ids))
        date_ph = ",".join("?" * len(target_dates))
        return conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, meses, valor, escala
                FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND consolidado=?
                AND grupo LIKE '%Valor Adicionado%'
                AND data_fim_exerc IN ({date_ph})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, consol, *target_dates),
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
                    AND grupo LIKE '%Valor Adicionado%'
                    ORDER BY data_fim_exerc DESC LIMIT ?""",
                (*empresa_ids, *codes, consolidado, periods),
            ).fetchall()

            if not year_rows:
                return {"status": "not_found",
                        "error": f"No DVA data found for '{company}' (company may not file DVA)"}

            target_dates = [r["data_fim_exerc"] for r in year_rows]
            rows = _fetch_dva_rows(conn, empresa_ids, target_dates, consolidado)
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

        # Get DFP annual DVA dates
        dfp_dates = dfp_conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({emp_ph})
                AND codigo IN ({code_ph})
                AND meses=12 AND consolidado=?
                AND grupo LIKE '%Valor Adicionado%'
                ORDER BY data_fim_exerc DESC""",
            (*empresa_ids, *codes, consolidado),
        ).fetchall()
        dfp_date_list = [r["data_fim_exerc"] for r in dfp_dates]
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        dfp_conn.close()

    # Get ITR quarterly DVA dates
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
                        AND grupo LIKE '%Valor Adicionado%'
                        ORDER BY data_fim_exerc DESC""",
                    (*itr_empresa_ids, *codes, consolidado),
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
                "error": f"No DVA data found for '{company}' (company may not file DVA)"}

    # Fetch rows from both DBs
    all_rows = []

    # DFP rows
    dfp_conn = connect_dfp(read_only=True)
    try:
        dfp_rows = _fetch_dva_rows(dfp_conn, empresa_ids, all_dates, consolidado)
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
                    itr_rows = _fetch_dva_rows(itr_conn, itr_empresa_ids, itr_dates_in_range, consolidado)
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
