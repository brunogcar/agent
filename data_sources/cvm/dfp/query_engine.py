"""data_sources/cvm/dfp/query_engine.py -- Query annual financial statements.

DFP data is annual (meses=12). This module queries the raw annual values:
  - Flow statements (DRE, DFC, DVA, DMPL): cumulative Jan→Dec values
  - Snapshot statements (BPA, BPP): point-in-time balances at Dec 31

NOTE: This data source returns RAW annual values. The trimestral transformation
(T1/T2/T3/T4 standalone quarters) and ratio computation (margins, EBITDA)
belong in the skills/ layer, not here. Each data source stores clean raw data;
the skill layer combines dfp + itr to produce derived views.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_dfp
from data_sources.cvm._bridge import resolve_company, not_found_message
from data_sources.cvm.dfp.catalog import RESUMO_LOOKUP, MESES_LABELS


def query(
    company: str = "",
    grupo: str = "",
    codigo: str = "",
    anos: list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 5,
) -> dict:
    """Query annual DFP financial statements for a company.

    Args:
        company: B3 ticker, name fragment, or CNPJ. Required.
        grupo: Filter by statement group (BPA, BPP, DRE, DFC_MI, DFC_MD, DVA, DMPL).
               Empty = all groups.
        codigo: Filter by account code prefix (e.g., "1.01" for current assets).
                Empty = all codes.
        anos: Specific years to query. Default: last `limit_years` years.
        consolidado: 1=consolidated (default), 0=individual.
        limit_years: Max years to return when anos is None. Default: 5.

    Returns:
        Dict with company info + list of account entries grouped by year.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_dfp(read_only=True)
    try:
        # Resolve company
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": not_found_message(company)}

        # Build query
        placeholders = ",".join("?" * len(empresa_ids))
        params: list[Any] = list(empresa_ids) + [consolidado]

        where_parts = [f"c.id_empresa IN ({placeholders})", "c.consolidado = ?"]

        if grupo:
            where_parts.append("c.grupo LIKE ?")
            params.append(f"%{grupo}%")

        if codigo:
            where_parts.append("c.codigo LIKE ?")
            params.append(f"{codigo}%")

        # Year filter
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
               ORDER BY e.ano DESC, c.grupo, c.codigo""",
            params,
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No DFP data found for '{company}'"}

        # Group by year → grupo → code
        result: dict[str, dict] = {}
        for row in rows:
            ano = str(row["ano"])
            if ano not in result:
                result[ano] = {}
            grp = row["grupo"]
            if grp not in result[ano]:
                result[ano][grp] = []

            result[ano][grp].append({
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
            "form": "DFP",
            "periods": result,
        }

    finally:
        conn.close()


def resumo(
    company: str = "",
    anos: list[int] | None = None,
    consolidado: int = 1,
    limit_years: int = 10,
) -> dict:
    """Query summary annual metrics (key accounts only).

    Returns only the RESUMO_ACCOUNTS (Ativo Total, Receita, Lucro, EBIT, etc.)
    pivoted by year. This is the "resumo anual" view.

    Note: ratios (margins, EBITDA) are NOT computed here — that's the skill
    layer's job. This returns raw account values.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_dfp(read_only=True)
    try:
        empresa_ids, company_name = resolve_company(conn, company)
        if not empresa_ids:
            return {"status": "not_found", "error": not_found_message(company)}

        # Query only the RESUMO account codes
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
                 AND c.meses = 12
                 {where_year}
               ORDER BY e.ano DESC, c.codigo""",
            params,
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No DFP resumo data found for '{company}'"}

        # Pivot: {metric_label: {year: value}}
        result: dict[str, dict[str, float]] = {}
        for row in rows:
            code = row["codigo"]
            if code in RESUMO_LOOKUP:
                _, label = RESUMO_LOOKUP[code]
                ano = str(row["ano"])
                if label not in result:
                    result[label] = {}
                result[label][ano] = row["valor"]

        return {
            "status": "ok",
            "company": company_name,
            "cnpj": _get_cnpj(conn, empresa_ids[0]),
            "consolidado": consolidado,
            "form": "DFP",
            "metrics": result,
        }

    finally:
        conn.close()


def search(query: str = "", limit: int = 10) -> dict:
    """Search for companies by name fragment or CNPJ.

    Returns a list of matching companies with their CNPJ + available years.
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    conn = connect_dfp(read_only=True)
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
