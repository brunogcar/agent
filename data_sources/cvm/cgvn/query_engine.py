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


# ── [WebUI v1.26] filings() — the per-exercício history ──────────────────────
# The company page's Governança tab shows the score EVOLUTION across
# filings (PETR4 has 9: refs 2018-12-31..2026-12-31). The label the user
# reads is the EXERCÍCIO year (from cgvn_documents' Data_Fim_Exercicio_
# Social — the ref 2026-12-31 filing covers exercício 2025), NOT the
# Data_Referencia year. _query_* above only ever see the latest filing —
# this is the first read of the full history.


def filings(company: str = "") -> dict:
    """All CGVN filings for a company — one row per Data_Referencia.

    Joins cgvn_practices (per-filing adoption counts) with cgvn_documents
    (entrega date, exercício window, download link). Exercício label =
    the year of Data_Fim_Exercicio_Social; falls back to the ref year - 1
    when no document row matches (defensive — the practices table is the
    source of truth, documents is enrichment).

    Returns:
        {status, company, cnpj, count,
         filings: [{data_referencia, data_entrega, exercicio, link,
                    total, sim, nao, parcialmente, nao_se_aplica,
                    score_pct}] — newest first.}
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

        # CNPJ strip chain — same as _query_* above, aliased for p.
        rows = conn.execute(
            """SELECT p.Data_Referencia AS ref,
                       SUM(CASE WHEN p.Pratica_Adotada = 'Sim' THEN 1 ELSE 0 END) AS sim,
                       SUM(CASE WHEN p.Pratica_Adotada = 'Não' THEN 1 ELSE 0 END) AS nao,
                       SUM(CASE WHEN p.Pratica_Adotada = 'Parcialmente' THEN 1 ELSE 0 END) AS parcial,
                       SUM(CASE WHEN p.Pratica_Adotada = 'Não se Aplica' THEN 1 ELSE 0 END) AS nsa,
                       COUNT(*) AS total
                FROM cgvn_practices p
                WHERE REPLACE(REPLACE(REPLACE(p.CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
                GROUP BY p.Data_Referencia
                ORDER BY p.Data_Referencia DESC""",
            (cnpj,),
        ).fetchall()

        if not rows:
            return {"status": "not_found",
                    "error": f"No CGVN practices for '{company}'",
                    "cnpj": cnpj}

        # Document metadata per Data_Referencia (entrega, exercício, link).
        # Multiple versions can exist — keep the latest entrega.
        docs: dict[str, dict] = {}
        for d in conn.execute(
            """SELECT Data_Referencia AS ref, Data_Entrega AS entrega,
                       Data_Inicio_Exercicio_Social AS ini,
                       Data_Fim_Exercicio_Social AS fim, Link_Download AS link
                FROM cgvn_documents
                WHERE REPLACE(REPLACE(REPLACE(CNPJ_Companhia, '.', ''), '/', ''), '-', '') = ?
                ORDER BY Data_Entrega""",
            (cnpj,),
        ).fetchall():
            docs[d["ref"]] = dict(d)

        out = []
        for r in rows:
            ref = r["ref"]
            d = docs.get(ref) or {}
            total = r["total"] or 0
            # Exercício year: Data_Fim "2025-12-31" → 2025. Fallback:
            # ref year - 1 (the CGVN convention: ref = exercício + 1).
            exercicio = None
            fim = (d.get("fim") or "")[:4]
            if fim.isdigit():
                exercicio = int(fim)
            elif (ref or "")[:4].isdigit():
                exercicio = int(ref[:4]) - 1
            out.append({
                "data_referencia": ref,
                "data_entrega": d.get("entrega") or "",
                "exercicio": exercicio,
                "link": d.get("link") or "",
                "total": total,
                "sim": r["sim"] or 0,
                "nao": r["nao"] or 0,
                "parcialmente": r["parcial"] or 0,
                "nao_se_aplica": r["nsa"] or 0,
                "score_pct": round((r["sim"] or 0) / total, 4) if total else 0,
            })

        return {
            "status": "ok",
            "company": company,
            "cnpj": cnpj,
            "count": len(out),
            "filings": out,
        }

    finally:
        conn.close()
