"""data_sources/cvm/fre/query_engine.py -- Query FRE data (governance + ownership + compensation).

Unlike DFP/ITR (financial statements), FRE contains corporate governance data:
  - Shareholder composition (who owns the company)
  - Free float / shareholder counts
  - Executive/board compensation
  - Stock capital + share counts

These are point-in-time snapshots from annual filings, not period flows.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_fre, cnpj_digits
from data_sources.cvm._bridge import resolve_company, not_found_message, looks_like_ticker, _resolve_via_bridge


def _resolve_fre_company(conn: sqlite3.Connection, company: str) -> tuple[list[str], str]:
    """Resolve company to CNPJ(s) using FRE documentos table.

    FRE doesn't have an empresas table — it has documentos with cnpj.
    """
    if not company:
        return [], ""

    # Try ticker → bridge → CNPJ
    if looks_like_ticker(company):
        cnpj = _resolve_via_bridge(company)
        if cnpj:
            rows = conn.execute(
                "SELECT DISTINCT cnpj, nome FROM documentos WHERE cnpj=? ORDER BY dt_refer DESC",
                (cnpj,),
            ).fetchall()
            if rows:
                return [r["cnpj"] for r in rows], rows[0]["nome"]

    # Try CNPJ
    cnpj = cnpj_digits(company)
    if cnpj:
        rows = conn.execute(
            "SELECT DISTINCT cnpj, nome FROM documentos WHERE cnpj=? ORDER BY dt_refer DESC",
            (cnpj,),
        ).fetchall()
        if rows:
            return [r["cnpj"] for r in rows], rows[0]["nome"]

    # Try name fragment
    rows = conn.execute(
        "SELECT DISTINCT cnpj, nome FROM documentos WHERE nome LIKE ? ORDER BY dt_refer DESC LIMIT 20",
        (f"%{company}%",),
    ).fetchall()
    if rows:
        return list(set(r["cnpj"] for r in rows)), rows[0]["nome"]

    return [], ""


def shareholders(company: str = "", limit: int = 50) -> dict:
    """Query shareholder composition for a company.

    Returns: list of shareholders with their ownership % (ON/PN/total).
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_fre(read_only=True)
    try:
        cnpjs, company_name = _resolve_fre_company(conn, company)
        if not cnpjs:
            return {"status": "not_found", "error": not_found_message(company)}

        cnpj = cnpjs[0]
        placeholders = ",".join("?" * 1)

        rows = conn.execute(
            f"""SELECT acionista, cpf_cnpj_acionista, tipo_pessoa,
                      acionista_controlador, pct_on, pct_pn, pct_total,
                      qtd_on, qtd_pn, qtd_total,
                      data_referencia, versao, nome_companhia
               FROM posicao_acionaria
               WHERE cnpj = ?
               ORDER BY pct_total DESC
               LIMIT ?""",
            (cnpj, limit),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No shareholder data found for '{company}'"}

        return {
            "status": "ok",
            "company": rows[0]["nome_companhia"] if rows else company_name,
            "cnpj": cnpj,
            "data_referencia": rows[0]["data_referencia"] if rows else "",
            "shareholders": [{
                "acionista": r["acionista"],
                "cpf_cnpj": r["cpf_cnpj_acionista"],
                "tipo_pessoa": r["tipo_pessoa"],
                "controlador": r["acionista_controlador"],
                "pct_on": r["pct_on"],
                "pct_pn": r["pct_pn"],
                "pct_total": r["pct_total"],
                "qtd_on": r["qtd_on"],
                "qtd_pn": r["qtd_pn"],
                "qtd_total": r["qtd_total"],
            } for r in rows],
        }
    finally:
        conn.close()


def free_float(company: str = "") -> dict:
    """Query free float / shareholder distribution for a company."""
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_fre(read_only=True)
    try:
        cnpjs, company_name = _resolve_fre_company(conn, company)
        if not cnpjs:
            return {"status": "not_found", "error": not_found_message(company)}

        cnpj = cnpjs[0]
        rows = conn.execute(
            """SELECT * FROM distribuicao_capital WHERE cnpj=? ORDER BY data_referencia DESC""",
            (cnpj,),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No free float data for '{company}'"}

        return {
            "status": "ok",
            "company": rows[0]["nome_companhia"],
            "cnpj": cnpj,
            "periods": [{
                "data_referencia": r["data_referencia"],
                "pct_on_circulacao": r["pct_on_circulacao"],
                "pct_pn_circulacao": r["pct_pn_circulacao"],
                "pct_total_circulacao": r["pct_total_circulacao"],
                "qtd_on_circulacao": r["qtd_on_circulacao"],
                "qtd_pn_circulacao": r["qtd_pn_circulacao"],
                "qtd_total_circulacao": r["qtd_total_circulacao"],
                "qtd_acionistas_pf": r["qtd_acionistas_pf"],
                "qtd_acionistas_pj": r["qtd_acionistas_pj"],
                "qtd_acionistas_inst": r["qtd_acionistas_inst"],
                "data_ultima_assembleia": r["data_ultima_assembleia"],
            } for r in rows],
        }
    finally:
        conn.close()


def compensation(company: str = "") -> dict:
    """Query executive/board compensation for a company."""
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_fre(read_only=True)
    try:
        cnpjs, company_name = _resolve_fre_company(conn, company)
        if not cnpjs:
            return {"status": "not_found", "error": not_found_message(company)}

        cnpj = cnpjs[0]
        rows = conn.execute(
            """SELECT * FROM remuneracao_orgao WHERE cnpj=? ORDER BY data_referencia DESC""",
            (cnpj,),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No compensation data for '{company}'"}

        return {
            "status": "ok",
            "company": rows[0]["nome_companhia"],
            "cnpj": cnpj,
            "periods": [{
                "data_referencia": r["data_referencia"],
                "orgao": r["orgao"],
                "dt_ini_exercicio": r["dt_ini_exercicio"],
                "dt_fim_exercicio": r["dt_fim_exercicio"],
                "num_membros": r["num_membros"],
                "num_membros_remunerados": r["num_membros_remunerados"],
                "salario": r["salario"],
                "beneficios": r["beneficios"],
                "bonus": r["bonus"],
                "participacao_resultados": r["participacao_resultados"],
                "baseada_acoes": r["baseada_acoes"],
                "total_remuneracao": r["total_remuneracao"],
                "total_remuneracao_orgao": r["total_remuneracao_orgao"],
            } for r in rows],
        }
    finally:
        conn.close()


def capital(company: str = "") -> dict:
    """Query stock capital + share counts for a company."""
    if not company:
        return {"status": "error", "error": "company is required"}

    conn = connect_fre(read_only=True)
    try:
        cnpjs, company_name = _resolve_fre_company(conn, company)
        if not cnpjs:
            return {"status": "not_found", "error": not_found_message(company)}

        cnpj = cnpjs[0]
        rows = conn.execute(
            """SELECT * FROM capital_social WHERE cnpj=? ORDER BY data_referencia DESC""",
            (cnpj,),
        ).fetchall()

        if not rows:
            return {"status": "not_found", "error": f"No capital data for '{company}'"}

        return {
            "status": "ok",
            "company": rows[0]["nome_companhia"],
            "cnpj": cnpj,
            "periods": [{
                "data_referencia": r["data_referencia"],
                "tipo_capital": r["tipo_capital"],
                "valor_capital": r["valor_capital"],
                "qtd_acoes_on": r["qtd_acoes_on"],
                "qtd_acoes_pn": r["qtd_acoes_pn"],
                "qtd_acoes_total": r["qtd_acoes_total"],
                "data_aprovacao": r["data_aprovacao"],
            } for r in rows],
        }
    finally:
        conn.close()


def search(query: str = "", limit: int = 10) -> dict:
    """Search for companies by name fragment in the FRE database."""
    if not query:
        return {"status": "error", "error": "query is required"}

    conn = connect_fre(read_only=True)
    try:
        rows = conn.execute(
            """SELECT DISTINCT cnpj, nome, cd_cvm,
                      GROUP_CONCAT(DISTINCT ano_origem) as anos,
                      COUNT(DISTINCT ano_origem) as num_anos
               FROM documentos
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
