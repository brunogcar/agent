"""data_sources/cvm/_bridge.py -- Shared company resolution for ALL cvm sub-domains.

Resolves a user-provided company identifier (B3 ticker, name fragment, or CNPJ)
into empresa IDs in the DFP/ITR databases.

RESOLUTION ORDER
----------------
1. B3 ticker pattern (PETR4, VALE3) → bridge.db lookup (fast, unambiguous)
2. 14-digit CNPJ → direct dfp_itr.db query (no bridge needed)
3. Name fragment → LIKE search in empresas.nome (fallback)

The bridge (step 1) is optional — if bridge.db doesn't exist or the ticker
isn't found, we fall through to name search. This means all cvm data sources
work without the bridge, just with slightly less convenient input.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from data_sources.cvm._db import cnpj_digits, dfp_db_path, itr_db_path, bridge_db_path


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

    # Step 3: Name fragment (LIKE search)
    rows = conn.execute(
        "SELECT id, nome FROM empresas WHERE nome LIKE ? ORDER BY ano DESC LIMIT 50",
        (f"%{query}%",),
    ).fetchall()
    if rows:
        # Return ALL empresa_ids (one per year) — do NOT deduplicate by CNPJ.
        # The query layer needs all year IDs to build historical results.
        # Deduplicating by CNPJ would drop older years, making the query
        # return only the latest year.
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
