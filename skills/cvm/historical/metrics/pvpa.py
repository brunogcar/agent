"""metrics/pvpa.py — P/VPA (Price-to-Book) historical metric. STUB for future.

P/VPA = price / (patrimonio_liquido / shares)

To implement:
  1. Add a PL engine in engines/ that queries DFP BPP 2.03 (PL) at any date
     — similar to earnings.py but for balance sheet items
  2. Implement pvpa_at() and pvpa_history() using price + PL + shares engines
  3. Register "pvpa" in metrics/__init__.py METRICS dict
  4. Add report adapter if needed

Challenge: PL is a snapshot (BPA/BPP), not a flow. ITR has quarterly snapshots.
DFP has annual snapshots. Between snapshots, PL is constant.
"""

from __future__ import annotations


def pvpa_at(company: str, date: str) -> float | None:
    """TODO: P/VPA = price / (PL / shares). Not yet implemented."""
    return None


def pvpa_history(company: str, date_from: str, date_to: str) -> list[dict]:
    """TODO: Daily P/VPA series. Not yet implemented."""
    return []
