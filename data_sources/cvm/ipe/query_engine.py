"""data_sources/cvm/ipe/query_engine.py -- Query IPE material events.

IPE = Informações Periódicas e Eventuais (event index).
Query company events by name/ticker/CNPJ, category, keyword, or date range.

[WebUI v1.26] browse() — the faceted explorer backing the company page's
Informações Periódicas subtab. The WebUI needs what query() never offered:
EXACT-match filters (query() is LIKE-based — "Assembleia" would also match
"Assembleia de Credores"… fine for a tool search, wrong for a select box),
the Espécie/Ano filters, server-side pagination (a PETR4 carries ~4.700
events) and FACETS — the distinct values + counts co-occurring with the
current filter set, so the select boxes cascade (pick Tipo=AGO and the
Categoria facet narrows to Assembleia). Real-data conventions baked in:

  - Tipo/Espécie/Categoria can be EMPTY (72K of 502K rows carry no Tipo;
    ~31% carry no Assunto) — the client sends the sentinel "__none__"
    to filter for them; facets list the empty value as "" (the client
    labels it "— sem tipo —").
  - versao > 1 marks a reapresentação (45K rows) — shipped so the UI
    can badge it (NOT deduped: each version is its own protocolo).
  - ORDER BY data_entrega DESC, id DESC — deterministic pagination.
  - Facet ordering [v1.26 fix 1]: anos CHRONOLOGICAL (newest first),
    the rest by count (most-used first).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_ipe, cnpj_digits
from data_sources.cvm._bridge import looks_like_ticker, _resolve_via_bridge

# Sentinel the WebUI sends to filter for the EMPTY value of a facet field
# (an empty string means "no filter" — it can't also mean "empty value").
EMPTY_SENTINEL = "__none__"


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


# ── [WebUI v1.26] browse() — the faceted explorer ────────────────────────────

# Filterable facet fields → column. Ano ranks chronologically (v DESC
# — [v1.26 fix 1] the count-ordered select the user reported: "ano is
# completely out of order… seems sorted by the number of items"), the
# rest by count (most-used first, the natural select-box order).
_FACET_FIELDS = {
    "categorias": "categoria",
    "tipos": "tipo",
    "especies": "especie",
    "anos": "ano_origem",
}


def _company_cnpj(conn: sqlite3.Connection, company: str) -> str | None:
    """Resolve company → CNPJ (same chain as query(): digits → bridge →
    name LIKE). Shared by query()/browse() so both stay in lockstep."""
    cnpj = cnpj_digits(company)
    if cnpj:
        return cnpj
    if looks_like_ticker(company):
        bridge_cnpj, _cd_cvm = _resolve_via_bridge(company)
        if bridge_cnpj:
            return bridge_cnpj
    row = conn.execute(
        "SELECT cnpj FROM eventos WHERE upper(nome) LIKE ? LIMIT 1",
        (f"%{company.upper()}%",),
    ).fetchone()
    return row["cnpj"] if row else None


def _facet_condition(column: str, value: str) -> tuple[str, list]:
    """One exact-match facet filter → (SQL condition, params).

    EMPTY_SENTINEL selects the empty value (NULL or ''); anything else is
    an exact match (select boxes ship exact values — LIKE would let
    "Assembleia" leak "Assembleia de Credores").
    """
    if value == EMPTY_SENTINEL:
        return f"({column} IS NULL OR {column} = '')", []
    return f"{column} = ?", [value]


def browse(
    company: str = "",
    categoria: str = "",
    tipo: str = "",
    especie: str = "",
    keyword: str = "",
    ano: int | str = "",
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Browse ONE company's IPE events — exact filters + facets + pagination.

    Args:
        company: Company name fragment, CNPJ, or B3 ticker (via bridge).
        categoria/tipo/especie: EXACT match ("Todos" = ""). The sentinel
            EMPTY_SENTINEL ("__none__") filters for the empty value.
        keyword: Case-insensitive substring on assunto.
        ano: Year filter (ano_origem — the ZIP year, == data_entrega year).
        page: 1-based page number.
        per_page: Rows per page (capped at 100).

    Returns:
        {status, cnpj, nome, total, page, pages, per_page,
         events: [{data_entrega, data_referencia, categoria, tipo,
                   especie, assunto, versao, protocolo, link_download}],
         facets: {categorias: [{v, n}], tipos: [...], especies: [...],
                  anos: [...]}}
        Facet lists respect every filter EXCEPT their own field (standard
        faceted-search cascade). The empty value ships as "". Facet
        ordering: anos chronological (newest first), the rest by count
        (most-used first).
    """
    conn = connect_ipe(read_only=True)
    try:
        cnpj = _company_cnpj(conn, company)
        if not cnpj:
            return {"status": "not_found", "count": 0, "events": [],
                    "facets": {}, "message":
                    f"Companhia '{company}' não encontrada na base IPE."}

        conditions = ["cnpj = ?"]
        params: list = [cnpj]
        for value, column in ((categoria, "categoria"), (tipo, "tipo"),
                              (especie, "especie")):
            if value:
                c, p = _facet_condition(column, value)
                conditions.append(c)
                params.extend(p)
        if keyword:
            conditions.append("upper(assunto) LIKE ?")
            params.append(f"%{keyword.upper()}%")
        try:
            ano_int = int(ano) if str(ano).strip() not in ("", "None") else None
        except (TypeError, ValueError):
            ano_int = None
        if ano_int:
            conditions.append("ano_origem = ?")
            params.append(ano_int)

        where = "WHERE " + " AND ".join(conditions)

        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM eventos {where}", params
        ).fetchone()["n"]

        per_page = max(1, min(int(per_page or 25), 100))
        page = max(1, int(page or 1))
        pages = max(1, -(-total // per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT data_entrega, data_referencia, categoria, tipo,
                       especie, assunto, versao, protocolo, link_download, nome
                FROM eventos {where}
                ORDER BY data_entrega DESC, id DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

        # Facets — each field sees every filter EXCEPT its own (pick
        # Tipo=AGO and the Categoria facet narrows to Assembleia).
        facets: dict[str, list[dict]] = {}
        for facet_key, column in _FACET_FIELDS.items():
            f_conditions = ["cnpj = ?"]
            f_params: list = [cnpj]
            if column != "categoria" and categoria:
                c, p = _facet_condition("categoria", categoria)
                f_conditions.append(c); f_params.extend(p)
            if column != "tipo" and tipo:
                c, p = _facet_condition("tipo", tipo)
                f_conditions.append(c); f_params.extend(p)
            if column != "especie" and especie:
                c, p = _facet_condition("especie", especie)
                f_conditions.append(c); f_params.extend(p)
            if column != "ano_origem" and ano_int:
                f_conditions.append("ano_origem = ?")
                f_params.append(ano_int)
            if keyword:
                f_conditions.append("upper(assunto) LIKE ?")
                f_params.append(f"%{keyword.upper()}%")
            # [v1.26 fix 1] anos: CHRONOLOGICAL, newest first (ano_origem
            # is INTEGER — numeric DESC; a text ASC/DESC would still be
            # fine for 4-digit years, but numeric is explicit). The other
            # facets: most-used first.
            order = ("v DESC" if column == "ano_origem" else "n DESC, v ASC")
            frows = conn.execute(
                f"""SELECT {column} AS v, COUNT(*) AS n
                    FROM eventos WHERE {' AND '.join(f_conditions)}
                    GROUP BY {column} ORDER BY {order}""",
                f_params,
            ).fetchall()
            facets[facet_key] = [
                {"v": ("" if r["v"] is None else str(r["v"])), "n": r["n"]}
                for r in frows
            ]

        nome = rows[0]["nome"] if rows else ""
        if not nome:
            r = conn.execute(
                "SELECT nome FROM eventos WHERE cnpj = ? "
                "ORDER BY data_entrega DESC LIMIT 1", (cnpj,),
            ).fetchone()
            nome = r["nome"] if r else ""

        return {
            "status": "ok",
            "cnpj": cnpj,
            "nome": nome,
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "events": [{
                "data_entrega": r["data_entrega"],
                "data_referencia": r["data_referencia"],
                "categoria": r["categoria"] or "",
                "tipo": r["tipo"] or "",
                "especie": r["especie"] or "",
                "assunto": r["assunto"] or "",
                "versao": r["versao"],
                "protocolo": r["protocolo"],
                "link_download": r["link_download"] or "",
            } for r in rows],
            "facets": facets,
        }

    finally:
        conn.close()
