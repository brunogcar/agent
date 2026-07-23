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


def _resolve_via_bridge(ticker: str) -> tuple[str | None, str | None]:
    """Resolve a B3 ticker via bridge.db (ticker_map table).

    [v1.1] Now reads the full ticker_map row and returns (cnpj, cd_cvm).
    The bridge sync (data_sources/cvm/bridge/) populates this table from the
    dividends API (codeCVM) + CAD (CNPJ + names).

    Returns:
        (cnpj, cd_cvm) -- both may be None/empty if bridge.db doesn't exist,
        the ticker isn't found, or CAD didn't have the cd_cvm.
        cnpj is preferred for DFP/ITR joins; cd_cvm is a fallback (empresas
        has a cd_cvm column too).
    """
    bridge = bridge_db_path()
    if not bridge.exists():
        return None, None

    try:
        conn = sqlite3.connect(f"file:{bridge}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT cnpj, cd_cvm FROM ticker_map WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
        conn.close()
        if row:
            return row["cnpj"] or None, row["cd_cvm"] or None
    except Exception:
        pass
    return None, None


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


def _auto_sync_bridge(ticker: str) -> bool:
    """[v1.2] Auto-sync a ticker into bridge.db. Returns True on success.

    Called by resolve_company when a ticker isn't in bridge.db. Delegates to
    bridge.sync_engine.sync, which: fetches dividends (if needed) → CAD join →
    upserts bridge.db. If the sync fails (network error, etc.), returns False
    and the resolver falls through to other resolution methods.

    Wrapped in a try/except so resolver failures never crash the caller.
    """
    try:
        from data_sources.cvm.bridge.sync_engine import sync as bridge_sync
        result = bridge_sync(ticker=ticker, force=False)
        return result.get("status") == "ok"
    except Exception:
        return False


def resolve_company(
    conn: sqlite3.Connection,
    query: str,
    auto_sync: bool = True,
) -> tuple[list[int], str]:
    """Resolve a company identifier to empresa IDs in the connected DB.

    Args:
        conn: SQLite connection to dfp.db or itr.db.
        query: B3 ticker, CNPJ, or company name fragment.
        auto_sync: [v1.2] If True (default), auto-sync the bridge when a ticker
            isn't in bridge.db. This makes the first query for a new ticker
            slower (network fetch) but all subsequent queries instant. Set to
            False for batch operations or tests.

    Returns:
        (empresa_ids, company_name) — list of IDs + the best-matching name.
        ([], "") if not found.

    [v1.0.1 P2] If a name fragment matches multiple distinct companies
    (different CNPJs), returns ([], "") — the caller should surface a
    disambiguation error. This prevents silently merging data from
    unrelated companies.

    [v1.2] Auto-sync-on-demand: when a ticker isn't in bridge.db, the resolver
    calls bridge.sync_engine.sync(ticker=...) transparently, then retries.
    This means you can query DFP/ITR/FRE/IPE with any ticker without pre-syncing
    the bridge — the first query populates it.
    """
    if not query or not query.strip():
        return [], ""

    query = query.strip()

    # Step 1: B3 ticker → bridge → (cnpj, cd_cvm)
    if looks_like_ticker(query):
        cnpj, cd_cvm = _resolve_via_bridge(query)
        # 1a. Try CNPJ first (preferred join key)
        if cnpj:
            rows = conn.execute(
                "SELECT id, nome FROM empresas WHERE cnpj = ? ORDER BY ano DESC",
                (cnpj,),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                return ids, rows[0]["nome"]
        # 1b. [v1.1] Fallback: try cd_cvm (empresas has a cd_cvm column).
        #     This handles the case where the bridge has cd_cvm but no CNPJ
        #     (CAD miss / stale cad.db / very new listing).
        if cd_cvm:
            rows = conn.execute(
                "SELECT id, nome FROM empresas WHERE cd_cvm = ? ORDER BY ano DESC",
                (str(cd_cvm).strip(),),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                return ids, rows[0]["nome"]
        # 1c. [v1.2] Auto-sync-on-demand: if the ticker isn't in bridge.db at all
        #     (both cnpj and cd_cvm are None), automatically sync the bridge for
        #     this ticker, then retry. This makes the bridge self-healing — the
        #     first time a ticker is queried, it's fetched + bridged transparently.
        #     Subsequent queries hit the cache (instant).
        #     Disabled when auto_sync=False (e.g., tests, batch operations).
        if auto_sync and cnpj is None and cd_cvm is None:
            synced = _auto_sync_bridge(query)
            if synced:
                cnpj, cd_cvm = _resolve_via_bridge(query)
                if cnpj:
                    rows = conn.execute(
                        "SELECT id, nome FROM empresas WHERE cnpj = ? ORDER BY ano DESC",
                        (cnpj,),
                    ).fetchall()
                    if rows:
                        ids = [r["id"] for r in rows]
                        return ids, rows[0]["nome"]
                if cd_cvm:
                    rows = conn.execute(
                        "SELECT id, nome FROM empresas WHERE cd_cvm = ? ORDER BY ano DESC",
                        (str(cd_cvm).strip(),),
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
            f"bridge database (bridge.db). Sync it with: "
            f"data_source(domain='cvm', sub_domain='bridge', mode='sync', "
            f"params='{{\"ticker\":\"{query}\"}}'). "
            f"Or search by company name instead: mode='search', "
            f"params='{{\"query\":\"{query}\"}}'"
        )
    return f"Company '{query}' not found in the database."
