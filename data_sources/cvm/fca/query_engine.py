"""data_sources/cvm/fca/query_engine.py -- Query FCA registration + listed securities.

Query modes:
  query(company=...)           -- company registration + all listed securities
  query(ticker=...)            -- ticker -> CNPJ + listing segment (bridge primary source)
  query(foreign_listings=True) -- foreign listings (ADR) for a company
"""

from __future__ import annotations

from typing import Any

from data_sources.cvm._db import cnpj_digits
from data_sources.cvm.fca.catalog import connect


def query(
    company: str = "",
    ticker: str = "",
    foreign_listings: bool = False,
    **kwargs,
) -> dict:
    """Query FCA registration data + listed securities.

    Args:
        company: Ticker, CNPJ, or company name fragment. Used for general + foreign queries.
        ticker: If provided, resolve this ticker -> CNPJ + listing segment (bridge primary).
        foreign_listings: If True, return foreign listings (ADR) for the company.

    Returns:
        Dict with registration + securities data.
    """
    if not company and not ticker:
        return {"status": "error", "error": "company or ticker is required"}

    try:
        conn = connect(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        if ticker:
            return _query_ticker(conn, ticker)
        elif foreign_listings:
            return _query_foreign(conn, company)
        else:
            return _query_company(conn, company)
    finally:
        conn.close()


def _resolve_cnpj(conn, company: str) -> str | None:
    """Resolve company to CNPJ — try bridge, then direct CNPJ, then name search."""
    # Try direct CNPJ
    cnpj = cnpj_digits(company)
    if cnpj:
        return cnpj

    # Try ticker -> CNPJ via fca_valor_mobiliario
    if company.strip().upper():
        row = conn.execute(
            "SELECT DISTINCT REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') as cnpj "
            "FROM fca_valor_mobiliario WHERE UPPER(Codigo_Negociacao) = ? LIMIT 1",
            (company.strip().upper(),),
        ).fetchone()
        if row and row["cnpj"]:
            return row["cnpj"]

    # Try name fragment search
    rows = conn.execute(
        "SELECT DISTINCT REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') as cnpj "
        "FROM fca_geral WHERE UPPER(Nome_Empresarial) LIKE ? LIMIT 1",
        (f"%{company.upper()}%",),
    ).fetchall()
    if rows:
        return rows[0]["cnpj"]

    return None


def _query_ticker(conn, ticker: str) -> dict:
    """Resolve ticker -> CNPJ + listing segment (bridge primary source)."""
    ticker = ticker.strip().upper()

    # Get the latest filing for this ticker
    row = conn.execute(
        """SELECT v.CNPJ_Companhia, v.Codigo_Negociacao, v.Segmento,
                  v.Mercado, v.Valor_Mobiliario, v.Classe_Acao_Preferencial,
                  v.Composicao_BDR_Unit, v.Data_Inicio_Listagem,
                  v.Data_Fim_Listagem, v.Data_Referencia,
                  g.Nome_Empresarial, g.Setor_Atividade,
                  g.Especie_Controle_Acionario, g.Situacao_Emissor
           FROM fca_valor_mobiliario v
           LEFT JOIN fca_geral g ON
             REPLACE(REPLACE(REPLACE(v.CNPJ_Companhia,'.',''),'/',''),'-','') =
             REPLACE(REPLACE(REPLACE(g.CNPJ_Companhia,'.',''),'/',''),'-','')
             AND g.Data_Referencia = (
               SELECT MAX(g2.Data_Referencia) FROM fca_geral g2
               WHERE REPLACE(REPLACE(REPLACE(g2.CNPJ_Companhia,'.',''),'/',''),'-','') =
                     REPLACE(REPLACE(REPLACE(v.CNPJ_Companhia,'.',''),'/',''),'-','')
             )
           WHERE UPPER(v.Codigo_Negociacao) = ?
           ORDER BY v.Data_Referencia DESC LIMIT 1""",
        (ticker,),
    ).fetchone()

    if not row:
        return {"status": "not_found", "error": f"Ticker '{ticker}' not found in FCA",
                "ticker": ticker}

    cnpj = cnpj_digits(row["CNPJ_Companhia"]) if row["CNPJ_Companhia"] else None
    cd_cvm = None
    if cnpj:
        # Get CD_CVM from fca_geral
        cvm_row = conn.execute(
            "SELECT Codigo_CVM FROM fca_geral "
            "WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') = ? "
            "ORDER BY Data_Referencia DESC LIMIT 1",
            (cnpj,),
        ).fetchone()
        if cvm_row:
            cd_cvm = cvm_row["Codigo_CVM"]

    return {
        "status": "ok",
        "ticker": ticker,
        "cnpj": cnpj,
        "cd_cvm": cd_cvm,
        "segmento": row["Segmento"] or "",
        "mercado": row["Mercado"] or "",
        "valor_mobiliario": row["Valor_Mobiliario"] or "",
        "classe_preferencial": row["Classe_Acao_Preferencial"] or "",
        "composicao_bdr_unit": row["Composicao_BDR_Unit"] or "",
        "data_inicio_listagem": row["Data_Inicio_Listagem"] or "",
        "data_fim_listagem": row["Data_Fim_Listagem"] or "",
        "data_referencia": row["Data_Referencia"] or "",
        "nome_empresarial": row["Nome_Empresarial"] or "",
        "setor_atividade": row["Setor_Atividade"] or "",
        "especie_controle": row["Especie_Controle_Acionario"] or "",
        "situacao_emissor": row["Situacao_Emissor"] or "",
    }


def _query_company(conn, company: str) -> dict:
    """Company registration + all listed securities."""
    cnpj = _resolve_cnpj(conn, company)
    if not cnpj:
        return {"status": "not_found",
                "error": f"Company '{company}' not found in FCA database"}

    # Get latest registration data
    geral = conn.execute(
        """SELECT * FROM fca_geral
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') = ?
           ORDER BY Data_Referencia DESC LIMIT 1""",
        (cnpj,),
    ).fetchone()

    # Get all listed securities
    securities = conn.execute(
        """SELECT Codigo_Negociacao, Segmento, Mercado, Valor_Mobiliario,
                  Classe_Acao_Preferencial, Data_Inicio_Listagem,
                  Data_Fim_Listagem, Data_Referencia
           FROM fca_valor_mobiliario
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') = ?
           ORDER BY Data_Referencia DESC""",
        (cnpj,),
    ).fetchall()

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "registration": dict(geral) if geral else {},
        "securities": [dict(r) for r in securities],
        "security_count": len(securities),
    }


def _query_foreign(conn, company: str) -> dict:
    """Foreign listings (ADR) for a company."""
    cnpj = _resolve_cnpj(conn, company)
    if not cnpj:
        return {"status": "not_found",
                "error": f"Company '{company}' not found in FCA database"}

    rows = conn.execute(
        """SELECT Pais, Data_Admissao_Negociacao, Data_Referencia, Nome_Empresarial
           FROM fca_pais_estrangeiro
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia,'.',''),'/',''),'-','') = ?
           ORDER BY Data_Referencia DESC""",
        (cnpj,),
    ).fetchall()

    if not rows:
        return {"status": "not_found",
                "error": f"No foreign listings for '{company}'",
                "cnpj": cnpj}

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "foreign_listings": [dict(r) for r in rows],
        "count": len(rows),
    }
