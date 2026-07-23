"""data_sources/cvm/itr/query_engine.py -- Query quarterly financial statements.

ITR data is quarterly cumulative (meses=3/6/9). This module returns RAW
cumulative values — NOT standalone quarters.

Standalone quarter computation (T2 = H1 − Q1, T3 = 9M − H1, T4 = DFP_annual − 9M)
belongs in the skills/ layer, which combines ITR + DFP data.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_itr
from data_sources.cvm._bridge import resolve_company, not_found_message
from data_sources.cvm.itr.catalog import RESUMO_LOOKUP, MESES_LABELS


def query(
    company: str = "",
    grupo: str = "",
    codigo: str = "",
    anos: list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 3,
) -> dict:
    """Query quarterly ITR financial statements for a company.

    Returns RAW cumulative values (meses=3/6/9). NOT standalone quarters.

    Args:
        company: B3 ticker, name fragment, or CNPJ. Required.
        grupo: Filter by statement group. Empty = all.
        codigo: Filter by account code prefix. Empty = all.
        anos: Specific years. Default: last `limit_years` years.
        consolidado: 1=consolidated (default), 0=individual.
        limit_years: Max years when anos is None. Default: 3.

    Returns:
        Dict with company info + list of account entries grouped by period.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_itr(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": company_name or not_found_message(company)}

        placeholders = ",".join("?" * len(empresa_ids))
        params: list[Any] = list(empresa_ids) + [consolidado]

        where_parts = [f"c.id_empresa IN ({placeholders})", "c.consolidado = ?"]

        if grupo:
            where_parts.append("c.grupo LIKE ?")
            params.append(f"%{grupo}%")

        if codigo:
            where_parts.append("c.codigo LIKE ?")
            params.append(f"{codigo}%")

        if anos:
            year_placeholders = ",".join("?" * len(anos))
            where_parts.append(f"e.ano IN ({year_placeholders})")
            params.extend(anos)
        else:
            where_parts.append(
                f"e.ano >= (SELECT MAX(ano) FROM empresas WHERE id IN ({placeholders})) - ?"
            )
            params.extend(empresa_ids)
            params.append(limit_years - 1)

        where_clause = " AND ".join(where_parts)

        rows = conn.execute(
            f"""SELECT c.codigo, c.descricao, c.grupo, c.data_ini_exerc,
                      c.data_fim_exerc, c.meses, c.valor, c.escala, c.moeda,
                      e.ano
               FROM contas c
               JOIN empresas e ON c.id_empresa = e.id
               WHERE {where_clause}
               ORDER BY e.ano DESC, c.data_fim_exerc DESC, c.grupo, c.codigo""",
            params,
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No ITR data found for '{company}'"}

        # Group by period (data_fim_exerc) → grupo → code
        result: dict[str, dict] = {}
        for row in rows:
            period = row["data_fim_exerc"]
            if period not in result:
                result[period] = {
                    "ano": row["ano"],
                    "meses": row["meses"],
                    "period_label": MESES_LABELS.get(row["meses"], f"{row['meses']}m"),
                }
            grp = row["grupo"]
            if grp not in result[period]:
                result[period][grp] = []

            result[period][grp].append({
                "codigo": row["codigo"],
                "descricao": row["descricao"],
                "valor": row["valor"],
                "data_ini_exerc": row["data_ini_exerc"],
                "data_fim_exerc": row["data_fim_exerc"],
                "meses": row["meses"],
                "escala": row["escala"],
                "moeda": row["moeda"],
            })

        return {
            "status": "ok",
            "company": company_name,
            "cnpj": _get_cnpj(conn, empresa_ids[0]),
            "consolidado": consolidado,
            "form": "ITR",
            "note": "Values are CUMULATIVE (Jan→period end), NOT standalone quarters.",
            "periods": result,
        }

    finally:
        conn.close()


def resumo(
    company: str = "",
    anos: list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 3,
) -> dict:
    """Query summary quarterly metrics (key accounts only, cumulative)."""
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_itr(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": company_name or not_found_message(company)}

        resumo_codes = list(RESUMO_LOOKUP.keys())
        code_placeholders = ",".join("?" * len(resumo_codes))
        emp_placeholders = ",".join("?" * len(empresa_ids))

        params: list[Any] = list(empresa_ids) + [consolidado] + resumo_codes

        where_year = ""
        if anos:
            year_placeholders = ",".join("?" * len(anos))
            where_year = f"AND e.ano IN ({year_placeholders})"
            params.extend(anos)
        else:
            where_year = (
                f"AND e.ano >= (SELECT MAX(ano) FROM empresas WHERE id IN ({emp_placeholders})) - ?"
            )
            params.extend(empresa_ids)
            params.append(limit_years - 1)

        rows = conn.execute(
            f"""SELECT c.codigo, c.descricao, c.grupo, c.valor, c.meses,
                      c.data_ini_exerc, c.data_fim_exerc, e.ano
               FROM contas c
               JOIN empresas e ON c.id_empresa = e.id
               WHERE c.id_empresa IN ({emp_placeholders})
                 AND c.consolidado = ?
                 AND c.codigo IN ({code_placeholders})
                 AND c.meses IN (3, 6, 9)
                 {where_year}
               ORDER BY e.ano DESC, c.data_fim_exerc DESC, c.codigo""",
            params,
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No ITR resumo data found for '{company}'"}

        # Pivot: {metric_label: {period: value}}
        result: dict[str, dict[str, float]] = {}
        for row in rows:
            code = row["codigo"]
            if code in RESUMO_LOOKUP:
                _, label = RESUMO_LOOKUP[code]
                period = row["data_fim_exerc"]
                if label not in result:
                    result[label] = {}
                result[label][period] = row["valor"]

        return {
            "status": "ok",
            "company": company_name,
            "cnpj": _get_cnpj(conn, empresa_ids[0]),
            "consolidado": consolidado,
            "form": "ITR",
            "note": "Values are CUMULATIVE (Jan→period end), NOT standalone quarters.",
            "metrics": result,
        }

    finally:
        conn.close()


def search(query: str = "", limit: int = 10) -> dict:
    """Search for companies by name fragment or CNPJ in the ITR database."""
    if not query:
        return {"status": "error", "error": "query is required"}

    conn = connect_itr(read_only=True)
    try:
        rows = conn.execute(
            """SELECT DISTINCT cnpj, nome, cd_cvm,
                      GROUP_CONCAT(DISTINCT ano) as anos,
                      COUNT(DISTINCT ano) as num_anos
               FROM empresas
               WHERE nome LIKE ? OR cnpj LIKE ?
               GROUP BY cnpj
               ORDER BY num_anos DESC
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
                "num_anos": r["num_anos"],
            } for r in rows],
        }

    finally:
        conn.close()


def _get_cnpj(conn: sqlite3.Connection, empresa_id: int) -> str:
    """Get the CNPJ for an empresa_id."""
    row = conn.execute(
        "SELECT cnpj FROM empresas WHERE id = ?", (empresa_id,)
    ).fetchone()
    return row["cnpj"] if row else ""
