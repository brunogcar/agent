"""data_sources/cvm/cgvn/query_engine.py -- Query governance practices.

Query modes:
  query(company=...)           -- all practices for latest filing
  query(company=..., score=True) -- governance score (% adopted, partial, not adopted)
  query(company=..., by_chapter=True) -- grouped by chapter
"""

from __future__ import annotations

from typing import Any

from data_sources.cvm._db import cnpj_digits
from data_sources.cvm._bridge import _resolve_via_bridge, _auto_sync_bridge
from data_sources.cvm._db import connect_cgvn


def query(
    company: str = "",
    score: bool = False,
    by_chapter: bool = False,
    **kwargs,
) -> dict:
    """Query governance practices for a company.

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
        score: If True, return governance score (% Sim/Não/Parcialmente).
        by_chapter: If True, group practices by chapter (Capitulo).

    Returns:
        Dict with governance practices.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    try:
        conn = connect_cgvn(read_only=True)
    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}

    try:
        cnpj = _resolve_company_cnpj(conn, company)
        if not cnpj:
            return {"status": "not_found",
                    "error": f"Company '{company}' not found in CGVN database"}

        if score:
            return _query_score(conn, cnpj, company)
        elif by_chapter:
            return _query_by_chapter(conn, cnpj, company)
        else:
            return _query_practices(conn, cnpj, company)
    finally:
        conn.close()


def _resolve_company_cnpj(conn, company: str) -> str | None:
    """Resolve company to CNPJ — try bridge first, then direct lookup."""
    if company.replace(".", "").replace("/", "").replace("-", "").isdigit():
        return cnpj_digits(company)

    cnpj, _ = _resolve_via_bridge(company)
    if not cnpj:
        _auto_sync_bridge(company)
        cnpj, _ = _resolve_via_bridge(company)
    if cnpj:
        return cnpj

    # Try name fragment search
    rows = conn.execute(
        "SELECT DISTINCT CNPJ_Companhia FROM cgvn_practices "
        "WHERE Nome_Empresarial LIKE ? LIMIT 1",
        (f"%{company.upper()}%",),
    ).fetchall()
    if rows:
        return rows[0]["CNPJ_Companhia"]

    return None


def _query_practices(conn, cnpj: str, company: str) -> dict:
    """All governance practices for the latest filing."""
    # Get the latest Data_Referencia for this company
    latest = conn.execute(
        "SELECT MAX(Data_Referencia) as max_date FROM cgvn_practices "
        "WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?",
        (cnpj,),
    ).fetchone()

    if not latest or not latest["max_date"]:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    data_ref = latest["max_date"]

    rows = conn.execute(
        """SELECT ID_Item, Pratica_Recomendada, Pratica_Adotada,
                  Capitulo, Principio, Explicacao, Data_Referencia
           FROM cgvn_practices
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
             AND Data_Referencia = ?
           ORDER BY Capitulo, ID_Item""",
        (cnpj, data_ref),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "data_referencia": data_ref,
        "count": len(rows),
        "practices": [dict(r) for r in rows],
    }


def _query_score(conn, cnpj: str, company: str) -> dict:
    """Governance score — % of practices adopted (Sim/Não/Parcialmente)."""
    latest = conn.execute(
        "SELECT MAX(Data_Referencia) as max_date FROM cgvn_practices "
        "WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?",
        (cnpj,),
    ).fetchone()

    if not latest or not latest["max_date"]:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    data_ref = latest["max_date"]

    rows = conn.execute(
        """SELECT Pratica_Adotada, COUNT(*) as cnt
           FROM cgvn_practices
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
             AND Data_Referencia = ?
           GROUP BY Pratica_Adotada""",
        (cnpj, data_ref),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    total = sum(r["cnt"] for r in rows)
    counts = {r["Pratica_Adotada"]: r["cnt"] for r in rows}

    sim = counts.get("Sim", 0)
    nao = counts.get("Não", 0)
    parcial = counts.get("Parcialmente", 0)

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "data_referencia": data_ref,
        "total_practices": total,
        "adopted_sim": sim,
        "adopted_nao": nao,
        "adopted_parcialmente": parcial,
        "score_pct": round(sim / total, 4) if total > 0 else 0,
        "partial_pct": round(parcial / total, 4) if total > 0 else 0,
        "not_adopted_pct": round(nao / total, 4) if total > 0 else 0,
        "counts": counts,
    }


def _query_by_chapter(conn, cnpj: str, company: str) -> dict:
    """Practices grouped by chapter (Capitulo)."""
    latest = conn.execute(
        "SELECT MAX(Data_Referencia) as max_date FROM cgvn_practices "
        "WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?",
        (cnpj,),
    ).fetchone()

    if not latest or not latest["max_date"]:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    data_ref = latest["max_date"]

    rows = conn.execute(
        """SELECT Capitulo,
                  COUNT(*) as total,
                  SUM(CASE WHEN Pratica_Adotada = 'Sim' THEN 1 ELSE 0 END) as adopted,
                  SUM(CASE WHEN Pratica_Adotada = 'Não' THEN 1 ELSE 0 END) as not_adopted,
                  SUM(CASE WHEN Pratica_Adotada = 'Parcialmente' THEN 1 ELSE 0 END) as partial
           FROM cgvn_practices
           WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
             AND Data_Referencia = ?
           GROUP BY Capitulo
           ORDER BY Capitulo""",
        (cnpj, data_ref),
    ).fetchall()

    if not rows:
        return {"status": "not_found", "error": f"No CGVN practices for '{company}'",
                "cnpj": cnpj}

    return {
        "status": "ok",
        "company": company,
        "cnpj": cnpj,
        "data_referencia": data_ref,
        "count": len(rows),
        "by_chapter": [dict(r) for r in rows],
    }
