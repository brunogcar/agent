"""data_sources/cvm/vlmo/query_engine.py -- Query insider trading movements.

Query modes:
  query(company=...)     -- recent insider transactions for a company
  query(company=..., by_role=True) -- grouped by role (director, officer, etc.)
  query(company=..., summary=True) -- net buy/sell summary per month
"""

from __future__ import annotations

from typing import Any

from data_sources.cvm._db import cnpj_digits
from data_sources.cvm._bridge import _resolve_via_bridge, _auto_sync_bridge
from data_sources.cvm._db import connect_vlmo


def query(
    company: str = "",
    limit: int = 50,
    by_role: bool = False,
    summary: bool = False,
    **kwargs,
) -> dict:
    """Query insider trading movements for a company.

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
        limit: Max results. Default: 50.
        by_role: If True, group results by role (Tipo_Cargo).
        summary: If True, return net buy/sell summary per month.

    Returns:
        Dict with insider trading movements.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    try:
        conn = connect_vlmo(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        # Resolve company -> CNPJ
        cnpj = _resolve_company_cnpj(conn, company)
        if not cnpj:
            return {"status": "not_found",
                    "error": f"Company '{company}' not found in VLMO database"}

        if summary:
            return _query_summary(conn, cnpj, company)
        elif by_role:
            return _query_by_role(conn, cnpj, company, limit)
        else:
            return _query_history(conn, cnpj, company, limit)
    finally:
        conn.close()


def _resolve_company_cnpj(conn, company: str) -> str | None:
    """Resolve company to CNPJ — try bridge first, then direct lookup."""
    # Try bridge (ticker -> CNPJ)
    if company.replace(".", "").replace("/", "").replace("-", "").isdigit():
        # It's a CNPJ
        return cnpj_digits(company)

    cnpj, _ = _resolve_via_bridge(company)
    if not cnpj:
        _auto_sync_bridge(company)
        cnpj, _ = _resolve_via_bridge(company)
    if cnpj:
        return cnpj

    # Try name fragment search in VLMO documents
    rows = conn.execute(
        "SELECT DISTINCT CNPJ_Companhia FROM vlmo_movements "
        "WHERE Nome_Companhia LIKE ? LIMIT 1",
        (f"%{company.upper()}%",),
    ).fetchall()
    if rows:
        return rows[0]["CNPJ_Companhia"]

    return None


def _query_history(conn, cnpj: str, company: str, limit: int) -> dict:
    """Recent insider transactions, newest-first."""
    # Normalize CNPJ for comparison (VLMO may have formatted CNPJs)
    rows = conn.execute(
        """SELECT Data_Movimentacao, Tipo_Cargo, Empresa, Tipo_Movimentacao,
                  Tipo_Ativo, Quantidade, Preco_Unitario, Volume,
                  Descricao_Movimentacao, Intermediario, Tipo_Operacao,
                  Caracteristica_Valor_Mobiliario, Data_Referencia
           FROM vlmo_movements
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
           ORDER BY Data_Movimentacao DESC
           LIMIT ?""",
        (cnpj, limit),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No insider movements for '{company}'",
                "cnpj": cnpj}

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "count": len(rows),
        "movements": [dict(r) for r in rows],
    }


def _query_by_role(conn, cnpj: str, company: str, limit: int) -> dict:
    """Group insider transactions by role (Tipo_Cargo)."""
    rows = conn.execute(
        """SELECT Tipo_Cargo,
                  COUNT(*) as transaction_count,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Compra' THEN Quantidade ELSE 0 END) as total_bought,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Venda' THEN Quantidade ELSE 0 END) as total_sold,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Compra' THEN Volume ELSE 0 END) as volume_bought,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Venda' THEN Volume ELSE 0 END) as volume_sold,
                  MIN(Data_Movimentacao) as earliest_date,
                  MAX(Data_Movimentacao) as latest_date
           FROM vlmo_movements
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
           GROUP BY Tipo_Cargo
           ORDER BY volume_bought + volume_sold DESC
           LIMIT ?""",
        (cnpj, limit),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No insider movements for '{company}'",
                "cnpj": cnpj}

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "count": len(rows),
        "by_role": [dict(r) for r in rows],
    }


def _query_summary(conn, cnpj: str, company: str) -> dict:
    """Net buy/sell summary per month."""
    rows = conn.execute(
        """SELECT substr(Data_Movimentacao, 1, 7) as month,
                  COUNT(*) as transaction_count,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Compra' THEN Quantidade ELSE 0 END) as bought,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Venda' THEN Quantidade ELSE 0 END) as sold,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Compra' THEN Volume ELSE 0 END) as volume_bought,
                  SUM(CASE WHEN Tipo_Movimentacao = 'Venda' THEN Volume ELSE 0 END) as volume_sold
           FROM vlmo_movements
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
             AND Data_Movimentacao IS NOT NULL
           GROUP BY substr(Data_Movimentacao, 1, 7)
           ORDER BY month DESC
           LIMIT 24""",
        (cnpj,),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No insider movements for '{company}'",
                "cnpj": cnpj}

    # Compute net for each month
    monthly = []
    for r in rows:
        d = dict(r)
        d["net_shares"] = (d["bought"] or 0) - (d["sold"] or 0)
        d["net_volume"] = (d["volume_bought"] or 0) - (d["volume_sold"] or 0)
        monthly.append(d)

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "count": len(monthly),
        "monthly": monthly,
    }
