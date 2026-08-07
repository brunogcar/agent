"""skills/cvm/calculations/engines/dfc/ -- DFC (Demonstração de Fluxo de
Caixa) engines.

All DFC engines live in this subfolder. The subfolder provides the namespace
(no collision with BPA `cash.py`, DRE `revenue.py`, etc.).

Auto-discovery is handled by _registry.py which globs engines/**/*.py
(including this subfolder).

ENGINES:
  capex.py         Capex (investing outflow)
  da.py            Depreciation & Amortization
  investing_cf.py  Investing cash flow
  operating_cf.py  Operating cash flow
  financing_cf.py  Financing cash flow
"""
