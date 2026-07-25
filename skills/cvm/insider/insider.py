"""skills/cvm/insider/insider.py -- Insider trading analysis skill.

Wraps data_sources.cvm.vlmo.query_engine with bridge auto-sync + freshness.

MODES
-----
  history (default) -- recent insider transactions (newest-first)
  by_role           -- grouped by role (director, officer, etc.)
  summary           -- net buy/sell per month (last 24 months)

NO SYNC
-------
Read-only. Assumes vlmo.db is already synced.
"""

from __future__ import annotations

from typing import Any


# ── Mode: history (default) ──────────────────────────────────────────────────

def history(company: str = "", limit: int = 50) -> dict:
    """Recent insider transactions (newest-first).

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
        limit: Max results. Default: 50.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, limit=limit)

    # Add freshness
    from skills.cvm._freshness import add_freshness
    return add_freshness(r)


# ── Mode: by_role ────────────────────────────────────────────────────────────

def by_role(company: str = "", limit: int = 50) -> dict:
    """Insider transactions grouped by role (Tipo_Cargo).

    Shows total bought/sold per role — directors, officers, controlling
    shareholders, etc.

    Args:
        company: Ticker, name, or CNPJ. Required.
        limit: Max roles. Default: 50.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, limit=limit, by_role=True)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)


# ── Mode: summary ────────────────────────────────────────────────────────────

def summary(company: str = "") -> dict:
    """Net buy/sell summary per month (last 24 months).

    Shows insider sentiment trend — are insiders net buyers or sellers?

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.vlmo.query_engine import query
    r = query(company=company, summary=True)

    # Compute overall net sentiment
    if r.get("status") == "ok" and r.get("monthly"):
        total_bought = sum(m.get("volume_bought") or 0 for m in r["monthly"])
        total_sold = sum(m.get("volume_sold") or 0 for m in r["monthly"])
        r["net_volume"] = total_bought - total_sold
        r["total_volume_bought"] = total_bought
        r["total_volume_sold"] = total_sold
        r["sentiment"] = ("buying" if total_bought > total_sold
                          else "selling" if total_sold > total_bought
                          else "neutral")

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)
