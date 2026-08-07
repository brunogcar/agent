"""skills/cvm/calculations/engines/bpa/ -- BPA (Balanço Patrimonial Ativo)
engines.

All BPA engines live in this subfolder. The subfolder provides the namespace
(no collision with BPP `debt.py`, DRE `revenue.py`, etc.).

Auto-discovery is handled by _registry.py which globs engines/**/*.py
(including this subfolder).

ENGINES:
  current_assets.py   Ativo Total (current portion)
  total_assets.py     Ativo Total
  cash.py             Caixa e equivalentes
  receivables.py      Contas a receber
  inventory.py        Estoques
  ppe.py              Imobilizado (PP&E)
  intangibles.py      Intangível
"""
