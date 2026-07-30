"""Mode: payable -- dividends declared but not yet paid (DFP BPP 2.01.05.02.01).

Balance sheet liability: "Dividendos e JCP a Pagar" — shows the amount
declared but still owed to shareholders as of the balance sheet date.

Returns: per fiscal year, the payable amount in BRL.

Registered as "payable" in skills.cvm.dividends._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.dividends._registry import register_mode


@register_mode(
    "payable",
    description="Dividends declared but not yet paid (DFP BPP 2.01.05.02.01).",
    include_in_all=False,
    params={
        "company": "str. Required.",
        "periods": "int. Number of fiscal years. Default: 5.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="dividends", mode="payable", params=\'{"company":"VALE3"}\')',
    ],
)
def payable(company: str = "", periods: int = 5) -> dict:
    """Dividends declared but not yet paid (DFP BPP 2.01.05.02.01).

    Balance sheet liability: "Dividendos e JCP a Pagar" — shows the amount
    declared but still owed to shareholders as of the balance sheet date.

    Returns: per fiscal year, the payable amount in BRL.
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

        placeholders_ids = ",".join("?" * len(empresa_ids))

        # BPP 2.01.05.02.01 (Dividendos e JCP a Pagar) + 2.01.05.02.02 (mínimo obrigatório)
        rows = conn.execute(
            f"""SELECT codigo, descricao, data_fim_exerc, valor, escala
                FROM contas
                WHERE id_empresa IN ({placeholders_ids})
                AND (codigo LIKE '2.01.05.02.01%' OR codigo LIKE '2.01.05.02.02%')
                AND meses=12
                ORDER BY data_fim_exerc DESC
                LIMIT ?""",
            (*empresa_ids, periods * 2),
        ).fetchall()

        if not rows:
            return {"status": "not_found",
                    "error": f"No BPP 2.01.05.02.* payable data found for '{company}'"}

        periods_data: dict[str, list] = {}
        for r in rows:
            date_key = r["data_fim_exerc"]
            if date_key not in periods_data:
                periods_data[date_key] = []
            # [v1.0.1] parse_escala handles "MIL", "MILHOES", "UNIDADE" strings
            escala = parse_escala(r["escala"])
            try:
                valor_brl = float(r["valor"] or 0) * escala
            except (TypeError, ValueError):
                valor_brl = 0.0
            periods_data[date_key].append({
                "codigo": r["codigo"],
                "descricao": r["descricao"],
                "valor_brl": valor_brl,
            })

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
