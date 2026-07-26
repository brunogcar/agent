"""skills/cvm/historical/metrics/__init__.py -- Ratio metrics for historical analysis.

A METRIC composes ENGINES. Each metric is a standalone module that imports
the engines it needs and combines them into a ratio:

  pe.py    — P/L   = price / (TTM earnings / shares)   [price + earnings + shares]
  vpa.py   — P/VPA = price / (PL / shares)             [price + pl + shares]
  ev_ebitda.py — EV/EBITDA (stub for future)

ENGINES vs METRICS — READ THIS BEFORE ADDING ANYTHING
-----------------------------------------------------
- ENGINES (in engines/): one per RAW QUANTITY. Each engine knows how to fetch
  ONE basic number at any historical date from its data source(s):
    - price.py    → daily close (COTAHIST)
    - earnings.py → TTM earnings (DFP + ITR derivation)
    - shares.py   → shares outstanding (FRE + investsite fallback)
    - pl.py       → Patrimônio Líquido snapshot (DFP + ITR BPP 2.03)
  Engines NEVER import each other. They are leaves.

- METRICS (in metrics/): one per RATIO. A metric imports 2+ engines and
  combines them. Metrics NEVER query CVM/B3 directly — that's the engine's job.
  This keeps the data access layer separate from the ratio math.

To add a new METRIC:
  1. Confirm the engines you need already exist. If not, add the ENGINE first
     (see engines/__init__.py).
  2. Create metrics/<name>.py with `<name>_at(ticker, date)` and
     `<name>_history(ticker, date_from, date_to)` functions.
  3. Add the metric to the METRICS registry below.
  4. Wire it into historical.py: ratio_history() dispatch + (optional) a
     dedicated <name>_history() mode + summary() metric-awareness.
  5. Add a report adapter in tools/report_ops/adapters/historical.py if you
     want chart/table rendering.
  6. Add tests in tests/skills/cvm/historical/.
"""
from __future__ import annotations

# Registry of available metrics (name → human-readable formula)
METRICS: dict[str, str] = {
    "pe":  "P/L (Price-to-Earnings) — price / (TTM earnings / shares)",
    "vpa": "P/VPA (Price-to-Book) — price / (PL / shares)",
    # Future metrics (stubs):
    # "ev_ebitda": "EV/EBITDA — (market_cap + debt - cash) / TTM EBITDA",
}
