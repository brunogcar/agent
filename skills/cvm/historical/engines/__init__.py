"""skills/cvm/historical/engines/__init__.py -- Data engines for historical ratios.

Each engine is a standalone module that fetches ONE raw quantity at any
historical date. Engines are LEAVES — they never import each other and never
import metrics. They can be imported independently by any skill (e.g.,
historical, future backtest, future screener).

Engine inventory:
  - price.py    — COTAHIST daily close prices: price_at(), price_series()
  - earnings.py — TTM earnings at any date (DFP + ITR derivation): ttm_earnings_at(), ttm_earnings_periods()
  - shares.py   — FRE shares outstanding at any date (+ investsite fallback): shares_at(), shares_periods()
  - pl.py       — Patrimônio Líquido snapshot at any date (DFP + ITR BPP 2.03): pl_at(), pl_periods()

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
  4. Add an entry to the engine inventory in this docstring.
  5. Do NOT register engines in a dict — they are imported by name by metrics.
  6. Add tests in tests/skills/cvm/historical/ (mock the DB connection).

NEVER import a metric from an engine. Engines are below metrics in the
dependency graph. A metric imports engines; never the reverse.
"""
