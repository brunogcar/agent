"""data_sources/cvm/ipe/query_engine.py -- Query IPE material events.

IPE = Informações Periódicas e Eventuais (event index).
Query company events by name/ticker/CNPJ, category, keyword, or date range.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_ipe, cnpj_digits
from data_sources.cvm._bridge import looks_like_ticker, _resolve_via_bridge


def query(
    company: str = "",
    categoria: str = "",
    tipo: str = "",
    keyword: str = "",
    data_from: str = "",
    data_to: str = "",
    limit: int = 20,
) -> dict:
    """Query IPE events for a company or by filters.

    Args:
        company: Company name fragment, CNPJ, or B3 ticker (via bridge).
        categoria: Filter by category (e.g., "Comunicado ao Mercado").
        tipo: Filter by type (e.g., "Aviso aos Acionistas").
        keyword: Filter by keyword in assunto (subject). Case-insensitive.
        data_from: Start date YYYY-MM-DD for data_entrega.
        data_to: End date YYYY-MM-DD.
        limit: Max rows. Default: 20.

    Returns:
        Dict with events list + count.
    """
    conn = connect_ipe(read_only=True)
    try:
        conditions = []
        params: list = []

        if company:
            cnpj = cnpj_digits(company)
            if cnpj:
                conditions.append("cnpj = ?")
                params.append(cnpj)
            elif looks_like_ticker(company):
                # [v1.2.1] _resolve_via_bridge now returns (cnpj, cd_cvm) tuple
                bridge_cnpj, _cd_cvm = _resolve_via_bridge(company)
                if bridge_cnpj:
                    conditions.append("cnpj = ?")
                    params.append(bridge_cnpj)
                else:
                    conditions.append("upper(nome) LIKE ?")
                    params.append(f"%{company.upper()}%")
            else:
                conditions.append("upper(nome) LIKE ?")
                params.append(f"%{company.upper()}%")

        if categoria:
            conditions.append("upper(categoria) LIKE ?")
            params.append(f"%{categoria.upper()}%")

        if tipo:
            conditions.append("upper(tipo) LIKE ?")
            params.append(f"%{tipo.upper()}%")

        if keyword:
            conditions.append("upper(assunto) LIKE ?")
            params.append(f"%{keyword.upper()}%")

        if data_from:
            conditions.append("data_entrega >= ?")
            params.append(data_from)

        if data_to:
            conditions.append("data_entrega <= ?")
            params.append(data_to)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = conn.execute(
            f"""SELECT cnpj, cd_cvm, nome, data_entrega, data_referencia,
                      categoria, tipo, especie, assunto,
                      versao, protocolo, link_download
               FROM eventos
               {where}
               ORDER BY data_entrega DESC
               LIMIT ?""",
            params + [limit],
        ).fetchall()

        if not rows:
            return {"status": "not_found", "count": 0, "events": []}

        return {
            "status": "ok",
            "count": len(rows),
            "events": [{
                "data_entrega": r["data_entrega"],
                "data_referencia": r["data_referencia"],
                "nome": r["nome"],
                "categoria": r["categoria"],
                "tipo": r["tipo"],
                "assunto": r["assunto"],
                "protocolo": r["protocolo"],
                "link_download": r["link_download"],
            } for r in rows],
        }

    finally:
        conn.close()


def search(query: str = "", limit: int = 10) -> dict:
    """Search for companies by name in the IPE database."""
    if not query:
        return {"status": "error", "error": "query is required"}

    conn = connect_ipe(read_only=True)
    try:
        rows = conn.execute(
            """SELECT DISTINCT cnpj, nome, cd_cvm,
                      GROUP_CONCAT(DISTINCT ano_origem) as anos,
                      COUNT(DISTINCT ano_origem) as num_anos,
                      COUNT(*) as num_events
               FROM eventos
               WHERE nome LIKE ? OR cnpj LIKE ?
               GROUP BY cnpj
               ORDER BY num_events DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No companies matching '{query}'"}

        return {
            "status": "ok",
            "query": query,
            "companies": [{
                "cnpj": r["cnpj"],
                "nome": r["nome"],
                "cd_cvm": r["cd_cvm"],
                "anos": [int(a) for a in r["anos"].split(",")] if r["anos"] else [],
                "num_events": r["num_events"],
            } for r in rows],
        }

    finally:
        conn.close()
