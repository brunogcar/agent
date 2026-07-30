"""Mode: equity_structure -- equity breakdown in BRL over N periods (DFP BPP).

Queries DFP BPP 2.03.* directly (capital social, reservas, lucros acumulados,
minority interest) over the last N fiscal years. Read-only — no sync.

Registered as "equity_structure" in skills.cvm.shareholders._registry.MODES
via the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.shareholders._registry import register_mode


@register_mode(
    "equity_structure",
    description="Equity breakdown in BRL (capital, reservas, minority) over N periods.",
    include_in_all=False,
    params={
        "company": "str. Required.",
        "periods": "int. Number of fiscal years. Default: 5.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params=\'{"company":"PETR4"}\')',
        'skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params=\'{"company":"VALE3","periods":3}\')',
    ],
)
def equity_structure(company: str = "", periods: int = 5) -> dict:
    """Query equity structure breakdown from DFP BPP 2.03.* over N periods.

    Returns total equity + components (capital social, reservas, lucros
    acumulados, minority interest) in BRL for the last N fiscal years.

    Codes (BPP 2.03.*):
      2.03      Patrimônio Líquido (total)
      2.03.01   Capital Social Realizado
      2.03.02   Reservas de Capital
      2.03.04   Reservas de Lucros
      2.03.05   Lucros/Prejuízos Acumulados
      2.03.09   Participação Não Controladores (minority interest)

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
        periods: Number of fiscal years to fetch (most recent first).
                 Default: 5.
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

        # [v1.2.1] CNPJ may be formatted in dfp.db — use REPLACE for robust match
        # resolve_company already handles this, so empresa_ids are correct.

        # BPP 2.03.* codes to fetch
        codes = ["2.03", "2.03.01", "2.03.02", "2.03.04", "2.03.05", "2.03.09"]
        placeholders_ids = ",".join("?" * len(empresa_ids))
        placeholders_codes = ",".join("?" * len(codes))

        # Get the last N distinct fiscal years (by data_fim_exerc)
        year_rows = conn.execute(
            f"SELECT DISTINCT data_fim_exerc FROM contas "
            f"WHERE id_empresa IN ({placeholders_ids}) "
            f"AND codigo IN ({placeholders_codes}) "
            f"AND meses=12 "
            f"ORDER BY data_fim_exerc DESC LIMIT ?",
            (*empresa_ids, *codes, periods),
        ).fetchall()

        if not year_rows:
            return {"status": "not_found",
                    "error": f"No BPP 2.03.* equity data found for '{company}'"}

        target_dates = [r["data_fim_exerc"] for r in year_rows]
        placeholders_dates = ",".join("?" * len(target_dates))

        # Fetch all rows for those dates
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

        # Organize by period
        periods_data: dict[str, dict] = {}
        code_labels = {
            "2.03": "Patrimônio Líquido Total",
            "2.03.01": "Capital Social Realizado",
            "2.03.02": "Reservas de Capital",
            "2.03.04": "Reservas de Lucros",
            "2.03.05": "Lucros/Prejuízos Acumulados",
            "2.03.09": "Participação Não Controladores",
        }

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
