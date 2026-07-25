"""skills/cvm/governance/governance.py -- Governance practices analysis skill.

Wraps data_sources.cvm.cgvn.query_engine with bridge auto-sync + freshness.

MODES
-----
  practices (default) -- all practices for latest filing
  score               -- governance score (% Sim/Não/Parcialmente)
  by_chapter          -- grouped by chapter with adoption counts

NO SYNC
-------
Read-only. Assumes cgvn.db is already synced.
"""

from __future__ import annotations

from typing import Any


# ── Mode: practices (default) ────────────────────────────────────────────────

def practices(company: str = "") -> dict:
    """All governance practices for the latest filing.

    Args:
        company: Ticker, name fragment, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)


# ── Mode: score ──────────────────────────────────────────────────────────────

def score(company: str = "") -> dict:
    """Governance score — % of practices adopted.

    Returns: total_practices, adopted_sim, adopted_nao, adopted_parcialmente,
    score_pct (% Sim), partial_pct, not_adopted_pct.

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company, score=True)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)


# ── Mode: by_chapter ─────────────────────────────────────────────────────────

def by_chapter(company: str = "") -> dict:
    """Practices grouped by chapter with adoption counts.

    Args:
        company: Ticker, name, or CNPJ. Required.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    from data_sources.cvm.cgvn.query_engine import query
    r = query(company=company, by_chapter=True)

    from skills.cvm._freshness import add_freshness
    return add_freshness(r)
