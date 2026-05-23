"""
skills/cvm/_bridge.py
Deploy to: D:\mcp\agent\skills\cvm\_bridge.py

Shared company resolution logic for ALL cvm sub-domains.
Imported by: cvm_dividends, cvm_shareholders, cvm_dfp_itr, cvm_register,
             and future cvm_dfp_itr, cvm_ipe, cvm_fre.

WHAT THIS REPLACES
------------------
Previously cvm_dividends.py and cvm_shareholders.py each had their own
inline copy of:
  _looks_like_ticker()
  _resolve_via_bridge()
  _resolve_company()

That was ~60 lines duplicated in every sub-domain. One change to the bridge
lookup logic required editing every file. Now there is one place.

HOW SUB-DOMAINS USE THIS
-------------------------
    from skills.cvm._bridge import resolve_company

    # In any cvm sub-domain that queries dfp_itr.db:
    ids, company_name = resolve_company(dfp_itr_conn, ticker_or_name)
    if not ids:
        return {"status": "not_found", ...}
    # use ids in dfp_itr queries

RESOLUTION ORDER
----------------
1. B3 ticker pattern (PETR4, VALE3) -> bridge.db lookup (fast, unambiguous)
2. 14-digit CNPJ -> direct dfp_itr.db query (no bridge needed)
3. Name fragment -> LIKE search in dfp_itr.db empresas.nome (fallback)

The bridge (step 1) is optional -- if bridge.db doesn't exist or the ticker
isn't found, we fall through to name search. This means all cvm skills work
without the bridge, just with slightly less convenient input (need company
name instead of ticker).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Optional


# ── Ticker heuristic ──────────────────────────────────────────────────────────

def looks_like_ticker(s: str) -> bool:
    """
    Return True if s looks like a B3 equity ticker.

    Pattern: exactly 4 uppercase letters + 1-2 digits + optional F
    Examples that match:   PETR4, VALE3, ITUB4, BBAS3, TAEE11, PETR4F
    Examples that don't:   PETROBRAS, 33000167000101, ABCD, petr (no digit)

    DECISION: We only match equity tickers here (not options like PETRH500,
    not futures like PETRH26). Options and futures are longer and would be
    passed to cvm_ skills as name/CNPJ, not as a ticker.

    Case-insensitive: "petr4" is normalized to "PETR4" before matching.
    """
    return bool(re.match(r"^[A-Z]{4}\d{1,2}F?$", s.upper().strip()))


# ── Bridge lookup ─────────────────────────────────────────────────────────────

def resolve_via_bridge(ticker: str) -> Optional[tuple[list[int], str]]:
    """
    Try to resolve a B3 ticker via bridge.db.

    Returns (dfp_itr_ids, denom_social) if found.
    Returns None if bridge.db doesn't exist, ticker not found, or any error.

    DECISION: All errors are silently swallowed and return None.
    The bridge is an enhancement, not a hard dependency. If bridge.db
    hasn't been synced yet, cvm skills fall through to name search.
    The user gets a slightly worse experience (must use company name)
    but the skill still works.

    DECISION: Import b3_cvm lazily inside the function.
    This avoids a circular import (cvm -> b3 -> cvm would be circular
    if b3_cvm imported from cvm). Lazy import happens at call time only.
    """
    try:
        from skills.b3.b3_cvm.b3_cvm import resolve_by_ticker
        result = resolve_by_ticker(ticker)
        if result and result.get("dfp_itr_ids"):
            return result["dfp_itr_ids"], result.get("denom_social", ticker)
        if result:
            # Ticker found in bridge but has no dfp_itr data
            # Return empty list with name so caller can give helpful error
            return [], result.get("denom_social", ticker)
    except ImportError:
        pass  # b3_cvm skill not installed
    except Exception:
        pass  # bridge.db missing, locked, corrupted etc.
    return None


# ── Main resolution function ──────────────────────────────────────────────────

def resolve_company(
    conn: sqlite3.Connection,
    ticker_or_name: str,
) -> tuple[list[int], str]:
    """
    Resolve any company identifier to (dfp_itr_ids, canonical_name).

    Args:
        conn:            Open dfp_itr.db connection (read-only).
        ticker_or_name:  Any of:
                           - B3 ticker:      "PETR4", "VALE3", "ITUB4"
                           - CNPJ 14 digits: "33000167000101"
                           - Name fragment:  "PETROBRAS", "VALE DO RIO"

    Returns:
        (list[int], str) -- (empresa_ids, canonical_name)
        ([], "")         -- if not found at any resolution step

    Resolution order:
      1. Ticker -> bridge.db (requires prior sync of b3_cvm)
      2. CNPJ (14 digits after stripping) -> dfp_itr.db direct
      3. Name LIKE -> dfp_itr.db fuzzy search

    DECISION: Return ALL empresa.ids for the CNPJ (not just latest).
    The consuming mode (_mode_annual, _mode_cash_paid etc.) filters
    by dt_refer to get the right period. Returning all ids gives callers
    maximum flexibility without coupling this function to period logic.

    DECISION: ids sorted ascending ([0]=oldest, [-1]=most recent).
    Consistent ordering avoids surprises when callers take ids[-1].
    """
    s = ticker_or_name.strip()
    if not s:
        return [], ""

    # ── Path 1: B3 ticker -> bridge.db ────────────────────────────────────────
    if looks_like_ticker(s):
        bridge_result = resolve_via_bridge(s.upper())
        if bridge_result is not None:
            ids, name = bridge_result
            return ids, name
        # Bridge unavailable or ticker not in bridge -> fall through to name search
        # (don't return yet -- maybe the 4-letter+digit string is also a name fragment)

    # ── Path 2: CNPJ (14 digits) -> dfp_itr.db ────────────────────────────────
    digits_only = re.sub(r"\D", "", s)
    if len(digits_only) == 14:
        rows = conn.execute(
            "SELECT DISTINCT id, nome FROM empresas "
            "WHERE cnpj = ? ORDER BY id ASC",
            (digits_only,),
        ).fetchall()
        if rows:
            return [r["id"] for r in rows], rows[0]["nome"]

    # ── Path 3: Name LIKE search -> dfp_itr.db ────────────────────────────────
    rows = conn.execute(
        "SELECT DISTINCT id, nome FROM empresas "
        "WHERE upper(nome) LIKE ? ORDER BY id ASC",
        (f"%{s.upper()}%",),
    ).fetchall()
    if rows:
        return [r["id"] for r in rows], rows[0]["nome"]

    return [], ""


# ── Error message helper ──────────────────────────────────────────────────────

def not_found_message(ticker_or_name: str) -> str:
    """
    Return a helpful not-found error message.
    Distinguishes ticker (bridge hint) from name (no bridge needed).
    """
    if looks_like_ticker(ticker_or_name):
        return (
            f"Empresa '{ticker_or_name}' nao encontrada. "
            f"Para usar ticker B3, sincronize o bridge primeiro: "
            f"skill(domain='b3_cvm', mode='sync'). "
            f"Ou use o nome CVM: ex. 'PETROBRAS'."
        )
    return (
        f"Empresa '{ticker_or_name}' nao encontrada em dfp_itr.db. "
        f"Use o nome CVM oficial, CNPJ (14 digitos), "
        f"ou ticker B3 (requer bridge sincronizado)."
    )
