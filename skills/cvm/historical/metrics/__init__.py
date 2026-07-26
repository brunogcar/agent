"""skills/cvm/historical/metrics/ -- Ratio metrics for historical analysis.

A METRIC composes ENGINES. Each metric is a standalone module that imports
the engines it needs and combines them into a ratio. Each metric produces
BOTH a per-share value AND a price ratio:
  - lpa.py: LPA (earnings/shares) + P/L (price/LPA)
  - vpa.py: VPA (pl/shares) + P/VPA (price/vpa)
  - dpa.py: DPA (dividends TTM) + Div Yield (DPA/price) + Payout (DPA/LPA)

AUTO-DISCOVERY
--------------
Auto-discovery is handled by the TOP-LEVEL _registry.py
(skills/cvm/historical/_registry.py), which globs both engines/*.py and
metrics/*.py. This file is a minimal docstring — no auto-discovery code here.

Each metric module self-registers via `register_metric(MetricSpec(...))`
at module level. The registry holds all specs.

METRIC VS ENGINE — READ THIS
----------------------------
- ENGINES (in engines/): one per RAW QUANTITY. Each engine fetches ONE basic
  number at any historical date from its data source(s). Engines are leaves.
- METRICS (here): one per RATIO. A metric imports 2+ engines and combines them.

To add a new METRIC:
  1. Confirm the engines you need already exist. If not, add the ENGINE first.
  2. Create metrics/<name>.py with:
     - <name>_at(ticker, date) -> per-share value
     - <ratio>_at(ticker, date) -> price ratio
     - <name>_history(ticker, date_from, date_to) -> list[dict]
  3. Call register_metric(MetricSpec(...)) at module level.
  4. That's it. The MANIFEST modes, ratio_history() dispatch, summary()
     metric-awareness, and chart adapter all auto-generate from the registry.
  5. Add tests in tests/skills/cvm/historical/test_<name>.py.
"""
