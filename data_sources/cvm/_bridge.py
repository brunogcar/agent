"""data_sources/cvm/_bridge.py -- Shared company resolution for ALL cvm sub-domains.

Resolves a user-provided company identifier (B3 ticker, name fragment, or CNPJ)
into empresa IDs in the DFP/ITR databases.

RESOLUTION ORDER
----------------
1. B3 ticker pattern (PETR4, VALE3) → bridge.db lookup (fast, unambiguous)
2. 14-digit CNPJ → direct DB query (no bridge needed)
3. Name fragment → CAD (cad.db) lookup first, then LIKE search in empresas.nome

[v1.0.1 P2 fix] Step 3 now guards against ambiguous name fragments matching
multiple DIFFERENT companies (different CNPJs). If multiple distinct CNPJs match,
returns a disambiguation error instead of silently merging data.

[v1.0.1 P2 fix] CAD (cad.db) is now the primary name resolver. When cad.db
exists, name lookups go through it first (exact DENOM_COMERC → exact DENOM_SOCIAL
→ LIKE search), returning a single CNPJ. This avoids the ambiguous-fragment
problem at the source. If cad.db doesn't exist, falls back to empresas.nome LIKE.

The bridge (step 1) is optional — if bridge.db doesn't exist or the ticker
isn't found, we fall through to CNPJ or name search. This means all cvm data
sources work without the bridge, just with slightly less convenient input.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from data_sources.cvm._db import cnpj_digits, dfp_db_path, itr_db_path, bridge_db_path, cad_db_path


_TICKER_RE = re.compile(r"^[A-Z]{4}\d{1,2}$")


def looks_like_ticker(s: str) -> bool:
    """Check if a string looks like a B3 ticker (PETR4, VALE3, etc.)."""
    if not s:
        return False
    s = s.strip().upper()
    return bool(_TICKER_RE.match(s))


def _resolve_via_bridge(ticker: str) -> str | None:
    """Resolve a B3 ticker to a CNPJ via the bridge.db.

    Returns the 14-digit CNPJ, or None if the bridge doesn't exist or the
    ticker isn't found.
    """
    bridge = bridge_db_path()
    if not bridge.exists():
        return None

    try:
        conn = sqlite3.connect(f"file:{bridge}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT cnpj FROM ticker_cnpj WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()
        if row:
            return row["cnpj"]
    except Exception:
        pass
    return None


def _resolve_via_cad(name: str) -> tuple[str | None, str | None]:
    """[v1.0.1] Resolve a name fragment to a single CNPJ via cad.db.

    Tries exact DENOM_COMERC → exact DENOM_SOCIAL → LIKE search.
    Returns (cnpj, company_name) if exactly 1 distinct CNPJ matches.
    Returns (None, None) if 0 matches or if multiple distinct CNPJs match
    (ambiguous — caller should ask for disambiguation).
    """
    cad = cad_db_path()
    if not cad.exists():
        return None, None

    try:
        conn = sqlite3.connect(f"file:{cad}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Try exact commercial name first
        row = conn.execute(
            "SELECT CNPJ_CIA, DENOM_SOCIAL FROM cia_aberta "
            "WHERE UPPER(DENOM_COMERC) = ? AND SIT = 'ATIVO' LIMIT 1",
            (name.upper(),),
        ).fetchone()
        if row:
            cnpj = cnpj_digits(row["CNPJ_CIA"])
            conn.close()
            return cnpj, row["DENOM_SOCIAL"]

        # Try exact social name
        row = conn.execute(
            "SELECT CNPJ_CIA, DENOM_SOCIAL FROM cia_aberta "
            "WHERE UPPER(DENOM_SOCIAL) = ? AND SIT = 'ATIVO' LIMIT 1",
            (name.upper(),),
        ).fetchone()
        if row:
            cnpj = cnpj_digits(row["CNPJ_CIA"])
            conn.close()
            return cnpj, row["DENOM_SOCIAL"]

        # LIKE search — check if multiple distinct CNPJs match
        rows = conn.execute(
            "SELECT DISTINCT REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','') as cnpj, "
            "DENOM_SOCIAL FROM cia_aberta "
            "WHERE (UPPER(DENOM_SOCIAL) LIKE ? OR UPPER(DENOM_COMERC) LIKE ?) "
            "AND SIT = 'ATIVO' LIMIT 5",
            (f"%{name.upper()}%", f"%{name.upper()}%"),
        ).fetchall()
        conn.close()

        if len(rows) == 1:
            return rows[0]["cnpj"], rows[0]["DENOM_SOCIAL"]
        # 0 matches or 2+ distinct CNPJs — ambiguous
        return None, None

    except Exception:
        return None, None


def resolve_company(
    conn: sqlite3.Connection,
    query: str,
) -> tuple[list[int], str]:
    """Resolve a company identifier to empresa IDs in the connected DB.

    Args:
        conn: SQLite connection to dfp.db or itr.db.
        query: B3 ticker, CNPJ, or company name fragment.

    Returns:
        (empresa_ids, company_name) — list of IDs + the best-matching name.
        ([], "") if not found.

    [v1.0.1 P2] If a name fragment matches multiple distinct companies
    (different CNPJs), returns ([], "") — the caller should surface a
    disambiguation error. This prevents silently merging data from
    unrelated companies.
    """
    if not query or not query.strip():
        return [], ""

    query = query.strip()

    # Step 1: B3 ticker → bridge → CNPJ
    if looks_like_ticker(query):
        cnpj = _resolve_via_bridge(query)
        if cnpj:
            rows = conn.execute(
                "SELECT id, nome FROM empresas WHERE cnpj = ? ORDER BY ano DESC",
                (cnpj,),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                return ids, rows[0]["nome"]

    # Step 2: CNPJ (14 digits)
    cnpj = cnpj_digits(query)
    if cnpj:
        rows = conn.execute(
            "SELECT id, nome FROM empresas WHERE cnpj = ? ORDER BY ano DESC",
            (cnpj,),
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            return ids, rows[0]["nome"]

    # Step 3a: [v1.0.1] Name → CAD (cad.db) → single CNPJ → DB
    cad_cnpj, cad_name = _resolve_via_cad(query)
    if cad_cnpj:
        rows = conn.execute(
            "SELECT id, nome FROM empresas WHERE cnpj = ? ORDER BY ano DESC",
            (cad_cnpj,),
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            return ids, rows[0]["nome"]
        # CNPJ found in CAD but not in DFP/ITR — company may not have filings
        return [], cad_name or ""

    # Step 3b: [v1.0.1] Fallback — LIKE search in empresas.nome (no CAD available)
    # Guard against ambiguous matches (multiple distinct CNPJs)
    rows = conn.execute(
        "SELECT id, nome, cnpj FROM empresas WHERE nome LIKE ? ORDER BY ano DESC LIMIT 50",
        (f"%{query}%",),
    ).fetchall()
    if rows:
        # Check if all rows belong to the same CNPJ (same company, different years)
        distinct_cnpjs = set(r["cnpj"] for r in rows)
        if len(distinct_cnpjs) > 1:
            # [v1.0.1 P2] Ambiguous — multiple different companies matched.
            # Return empty to signal disambiguation needed.
            company_names = list(set(r["nome"] for r in rows))[:5]
            return [], f"AMBIGUOUS: '{query}' matches {len(distinct_cnpjs)} companies: {company_names}. Use CNPJ or a more specific name."

        # Single company — return all year IDs
        ids = [r["id"] for r in rows]
        return ids, rows[0]["nome"]

    return [], ""


def not_found_message(query: str) -> str:
    """Return a helpful error message for a not-found company."""
    if looks_like_ticker(query):
        return (
            f"Company '{query}' not found. Ticker resolution requires the B3-CVM "
            f"bridge database (bridge.db). Try syncing the bridge, or search by "
            f"company name instead: mode='search', params='{{\"query\": \"{query}\"}}'"
        )
    return f"Company '{query}' not found in the database."
