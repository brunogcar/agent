"""skills/cvm/calculations/engines/bpp/ -- BPP (Balanço Patrimonial Passivo)
engines.

All BPP engines live in this subfolder. The subfolder provides the namespace
(no collision with BPA `cash.py`, DRE `revenue.py`, etc.).

Auto-discovery is handled by _registry.py which globs engines/**/*.py
(including this subfolder).

ENGINES:
  debt.py               Dívida (gross + net)
  pl.py                 Patrimônio Líquido
  payables.py           Contas a pagar
  current_liabilities.py Passivo Circulante
"""
