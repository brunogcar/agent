"""skills/cvm/historical/metrics/__init__.py -- Ratio metrics for historical analysis.

Each metric is a standalone module that imports the engines it needs:
  - pe.py       — P/L = price / (TTM earnings / shares)
  - pvpa.py     — P/VPA = price / (PL / shares) — stub for future
  - ev_ebitda.py — EV/EBITDA — stub for future

To add a new metric:
  1. Create a new file in metrics/ (e.g., psr.py)
  2. Import the engines you need (price, earnings, shares, or query DFP directly)
  3. Implement `metric_at(ticker, date)` and `metric_history(ticker, date_from, date_to)`
  4. Add the metric name to the METRICS registry in metrics/__init__.py
  5. Add a report adapter if you want chart/table rendering
"""
from __future__ import annotations

# Registry of available metrics
METRICS: dict[str, str] = {
    "pe": "P/L (Price-to-Earnings) — price / (TTM earnings / shares)",
    # Future metrics (stubs):
    # "pvpa": "P/VPA (Price-to-Book) — price / (PL / shares)",
    # "ev_ebitda": "EV/EBITDA — (market_cap + debt - cash) / TTM EBITDA",
}
