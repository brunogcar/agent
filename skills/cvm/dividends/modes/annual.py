"""Mode: annual -- annual declared dividend totals (DFP DVA 7.08.04.*).

DVA codes:
  7.08.04     Remuneração de Capitais Próprios (total)
  7.08.04.01  Juros sobre Capital Próprio (JCP)
  7.08.04.02  Dividendos
  7.08.04.03  Lucros Retidos / Prejuízos do Exercício

Returns: per fiscal year, Dividendos + JCP + total in BRL.

Registered as "annual" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.dividends._registry import register_mode


@register_mode(
    "annual",
    description="Annual declared dividend totals (Dividendos + JCP) from DFP DVA 7.08.04.*.",
    include_in_all=False,
    params={
        "company": "str. B3 ticker, name, or CNPJ. Required.",
        "periods": "int. Number of fiscal years. Default: 5.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="annual", params=\'{"company":"PETR4"}\')',
    ],
)
def annual(company: str = "", periods: int = 5) -> dict:
    """Annual declared dividend totals from DFP DVA 7.08.04.* per fiscal year.

    DVA codes:
      7.08.04     Remuneração de Capitais Próprios (total)
      7.08.04.01  Juros sobre Capital Próprio (JCP)
      7.08.04.02  Dividendos
      7.08.04.03  Lucros Retidos / Prejuízos do Exercício

    Returns: per fiscal year, Dividendos + JCP + total in BRL.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm._db import connect_dfp, parse_escala
    from data_sources.cvm._bridge import resolve_company

    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": f"Company '{company}' not found in DFP"}

        # DVA 7.08.04.* codes
        codes = ["7.08.04", "7.08.04.01", "7.08.04.02", "7.08.04.03"]
        placeholders_ids = ",".join("?" * len(empresa_ids))
        placeholders_codes = ",".join("?" * len(codes))

        # Get last N distinct fiscal years
        year_rows = conn.execute(
            f"""SELECT DISTINCT data_fim_exerc FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND codigo IN ({placeholders_codes})
                AND meses=12
                ORDER BY data_fim_exerc DESC LIMIT ?""",
            (*empresa_ids, *codes, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found",
                    "error": f"No DVA 7.08.04.* dividend data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        placeholders_dates = ",".join("?" * len(target_dates))

        rows = conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND codigo IN ({placeholders_codes})
                AND meses=12
                AND data_fim_exerc IN ({placeholders_dates})
                ORDER BY data_fim_exerc DESC, codigo""",
            (*empresa_ids, *codes, *target_dates),
        ).fetchall()

        code_labels = {
            "7.08.04": "Remuneração de Capitais Próprios (total)",
            "7.08.04.01": "Juros sobre Capital Próprio (JCP)",
            "7.08.04.02": "Dividendos",
            "7.08.04.03": "Lucros Retidos / Prejuízos do Exercício",
        }

        periods_data: dict[str, dict] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = {}
            # [v1.0.1] parse_escala handles "MIL", "MILHOES", "UNIDADE" strings
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key][r["codigo"]] = {
                "label": code_labels.get(r["codigo"], r["descricao"]),
                "valor_brl": valor_brl,
            }

        return {
            "status": "ok",
            "company": company_name,
            "periods": [
                {"data_fim_exerc": date, "accounts": periods_data[date]}
                for date in sorted(periods_data.keys(), reverse=True)
            ],
        }
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    finally:
        conn.close()
