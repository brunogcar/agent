"""skills/cvm/historical/engines/ -- Data engines for historical ratios.

Each engine is a standalone module that fetches ONE raw quantity at any
historical date. Engines are LEAVES — they never import each other and never
import metrics. They can be imported independently by any skill.

Engine inventory (auto-discovered by top-level _registry.py):
  - price.py     — COTAHIST daily close: price_at(), price_series()
  - earnings.py  — DFP + ITR TTM earnings: ttm_earnings_at(), ttm_earnings_periods()
  - shares.py    — FRE shares (+ investsite fallback): shares_at(), shares_periods()
  - pl.py        — DFP + ITR BPP 2.03 PL snapshot: pl_at(), pl_periods()
  - dividends.py — B3 cash_dividends DPA TTM: dividends_at(), dividends_periods()

AUTO-DISCOVERY
--------------
Auto-discovery is handled by the TOP-LEVEL _registry.py
(skills/cvm/historical/_registry.py), which globs both engines/*.py and
metrics/*.py. This file is a minimal docstring — no auto-discovery code here.

Each engine module self-registers via `register_engine(EngineSpec(...))` at
module level. The registry holds all specs.

ENGINE CONTRACT (every engine follows this shape):
  - `<quantity>_at(company, date) -> float | None`
      Return the value at the most recent data point <= date. None if no data.
  - `<quantity>_periods(company) -> list[dict]`
      Return all known data points as [{"date": "YYYY-MM-DD", "<quantity>": value}, ...]
      sorted oldest-first. Used by metrics for step-function optimization.

To add a new ENGINE:
  1. Create engines/<name>.py.
  2. Query your data source directly (CVM/B3/external). Apply parse_escala to
     raw CVM values. Use connect_dfp / connect_itr / connect_fre / etc. from
     data_sources/cvm/_db.py. Resolve tickers via _bridge.resolve_company().
  3. Implement `<name>_at(company, date)` and `<name>_periods(company)`.
  4. Call `register_engine(EngineSpec(...))` at module level.
  5. Add tests in tests/skills/cvm/historical/ (mock the DB connection).

NEVER import a metric from an engine. Engines are below metrics in the
dependency graph. A metric imports engines; never the reverse.
"""
