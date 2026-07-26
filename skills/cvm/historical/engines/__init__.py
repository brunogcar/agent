"""skills/cvm/historical/engines/__init__.py -- Data engines for historical ratios.

Each engine is a standalone module importable independently:
  - price.py    — COTAHIST daily close prices
  - earnings.py — TTM earnings at any date (DFP + ITR derivation)
  - shares.py   — FRE shares outstanding at any date

These engines are designed for reuse by future skills (e.g., backtest).
"""
