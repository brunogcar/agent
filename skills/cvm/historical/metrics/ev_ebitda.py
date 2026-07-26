"""metrics/ev_ebitda.py — EV/EBITDA historical metric. STUB for future.

EV/EBITDA = (market_cap + debt - cash) / TTM EBITDA

To implement:
  1. Add a balance_sheet engine in engines/ that queries DFP/ITR for:
     - divida_bruta (BPP 2.01.04 + 2.02.01)
     - caixa (BPA 1.01.01)
     - EBIT (DRE 3.05)
     - D&A (DFC 6.01.01.02)
     All at any date (TTM for flows, snapshot for balance sheet)
  2. EBITDA TTM = EBIT TTM + D&A TTM (same TTM derivation as earnings)
  3. EV = (price × shares) + debt - cash
  4. Implement ev_ebitda_at() and ev_ebitda_history()
  5. Register "ev_ebitda" in metrics/__init__.py METRICS dict

Challenge: needs 4 additional DFP/ITR accounts (not just 3.11).
The engines/earnings.py pattern can be generalized to a generic
"account_at(company, date, codigo)" engine.
"""

from __future__ import annotations


def ev_ebitda_at(company: str, date: str) -> float | None:
    """TODO: EV/EBITDA at a specific date. Not yet implemented."""
    return None


def ev_ebitda_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """TODO: Daily EV/EBITDA series. Not yet implemented."""
    return []
