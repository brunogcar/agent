"""data_sources/cvm/cad/query_engine.py -- Query CVM company register (cad.db).

Primary entry point for company resolution: ticker → CNPJ → CD_CVM → financial statements.
Also supports sector/status/control-type filtering for screening.

KEY USE CASE: Bridge resolution
  1. LLM provides a B3 ticker (e.g., "PETR4")
  2. b3_cvm bridge resolves ticker → CNPJ
  3. This module resolves CNPJ → CD_CVM + company name
  4. CD_CVM + CNPJ are used to query DFP/ITR/FRE/IPE

Without the bridge, users can search by name fragment or CNPJ directly.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data_sources.cvm._db import connect_cad, cnpj_digits
from data_sources.cvm.cad.catalog import ALL_COLS, DEFAULT_COLS


def lookup(
    cnpj: str = "",
    cd_cvm: str = "",
    name: str = "",
    full: bool = False,
) -> dict:
    """Look up a single company by CNPJ, CD_CVM, or name.

    Tries exact matches first, then partial. Returns the best match.

    Args:
        cnpj: Company CNPJ (formatted or numeric).
        cd_cvm: CVM internal code (e.g., "9512").
        name: Company name or fragment (searches both legal + commercial names).
        full: If True, return all 46 columns; default returns DEFAULT_COLS only.

    Returns:
        {status: "ok", company: {...}} or {status: "multiple", matches: [...]}
        or {status: "not_found", error: "..."}
    """
    conn = connect_cad(read_only=True)
    try:
        cols = ALL_COLS if full else DEFAULT_COLS
        select = ", ".join(cols)

        queries: list[str] = []
        params_list: list[list] = []

        if cnpj:
            cnpj_n = cnpj_digits(cnpj)
            if cnpj_n:
                # CNPJ in DB may be formatted; strip for comparison
                queries.append(
                    f"SELECT {select} FROM cia_aberta WHERE "
                    f"REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') = ? LIMIT 1"
                )
                params_list.append([cnpj_n])

        if cd_cvm:
            queries.append(f"SELECT {select} FROM cia_aberta WHERE CD_CVM = ? LIMIT 1")
            params_list.append([str(cd_cvm).strip()])

        if name:
            # Exact commercial name first, then partial
            queries.append(
                f"SELECT {select} FROM cia_aberta WHERE UPPER(DENOM_COMERC) = ? LIMIT 1"
            )
            params_list.append([name.upper()])
            queries.append(
                f"SELECT {select} FROM cia_aberta WHERE "
                f"(UPPER(DENOM_SOCIAL) LIKE ? OR UPPER(DENOM_COMERC) LIKE ?) LIMIT 5"
            )
            params_list.append([f"%{name.upper()}%", f"%{name.upper()}%"])

        for sql, params in zip(queries, params_list):
            rows = conn.execute(sql, params).fetchall()
            if rows:
                if len(rows) == 1:
                    return {"status": "ok", "company": dict(rows[0])}
                else:
                    return {
                        "status": "multiple",
                        "count": len(rows),
                        "matches": [dict(r) for r in rows],
                        "hint": "Use CNPJ or CD_CVM for exact lookup",
                    }

        return {
            "status": "not_found",
            "error": f"No company found for: cnpj={cnpj!r} cd_cvm={cd_cvm!r} name={name!r}",
        }
    finally:
        conn.close()


def search(
    name: str = "",
    setor: str = "",
    sit: str = "",
    sit_emissor: str = "",
    controle: str = "",
    uf: str = "",
    active_only: bool = True,
    limit: int = 20,
) -> dict:
    """Search companies with multiple filters.

    Args:
        name: Company name fragment (searches legal + commercial name).
        setor: Sector fragment (e.g., "Energia", "Bancos").
        sit: Exact registration status ("ATIVO", "CANCELADA").
        sit_emissor: Issuer situation fragment ("RECUPERACAO", "PRE-OPERACIONAL").
        controle: Ownership control ("PRIVADO", "ESTATAL", "ESTRANGEIRO").
        uf: State code ("SP", "RJ", "MG").
        active_only: Filter to SIT='ATIVO' only (default True).
        limit: Max results (default 20).

    Returns:
        {status: "ok", total_matches: N, returned: M, companies: [...]}
    """
    conn = connect_cad(read_only=True)
    try:
        parts: list[str] = []
        params: list = []

        if name:
            parts.append("(UPPER(DENOM_SOCIAL) LIKE ? OR UPPER(DENOM_COMERC) LIKE ?)")
            pct = f"%{name.upper()}%"
            params.extend([pct, pct])

        if setor:
            parts.append("UPPER(SETOR_ATIV) LIKE ?")
            params.append(f"%{setor.upper()}%")

        if sit:
            parts.append("UPPER(SIT) = ?")
            params.append(sit.upper())
        elif active_only:
            parts.append("SIT = 'ATIVO'")

        if sit_emissor:
            parts.append("UPPER(SIT_EMISSOR) LIKE ?")
            params.append(f"%{sit_emissor.upper()}%")

        if controle:
            parts.append("UPPER(CONTROLE_ACIONARIO) LIKE ?")
            params.append(f"%{controle.upper()}%")

        if uf:
            parts.append("UPPER(UF) = ?")
            params.append(uf.upper())

        where = f"WHERE {' AND '.join(parts)}" if parts else ""

        count = conn.execute(
            f"SELECT COUNT(*) FROM cia_aberta {where}", params
        ).fetchone()[0]

        cols = ", ".join(DEFAULT_COLS)
        rows = conn.execute(
            f"SELECT {cols} FROM cia_aberta {where} ORDER BY DENOM_COMERC LIMIT ?",
            params + [limit],
        ).fetchall()

        return {
            "status": "ok",
            "total_matches": count,
            "returned": len(rows),
            "companies": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def sectors() -> dict:
    """List all distinct sectors (SETOR_ATIV) with company counts."""
    conn = connect_cad(read_only=True)
    try:
        rows = conn.execute(
            "SELECT SETOR_ATIV, COUNT(*) as count FROM cia_aberta "
            "WHERE SIT='ATIVO' AND SETOR_ATIV != '' "
            "GROUP BY SETOR_ATIV ORDER BY count DESC"
        ).fetchall()
        return {
            "status": "ok",
            "sectors": [{"setor": r["SETOR_ATIV"], "count": r["count"]} for r in rows],
            "total": len(rows),
        }
    finally:
        conn.close()
