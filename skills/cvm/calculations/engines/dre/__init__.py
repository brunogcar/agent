"""skills/cvm/calculations/engines/dre/ -- DRE (Demonstração do Resultado
do Exercício) engines.

All DRE engines live in this subfolder. The subfolder provides the namespace
(no collision with BPA `cash.py`, DVA `revenue.py`, etc.).

Auto-discovery is handled by _registry.py which globs engines/**/*.py
(including this subfolder).

ENGINES:
  cogs.py              Custo dos Bens e/ou Serviços Vendidos (3.02)
  gross_profit.py      Lucro Bruto (3.03)
  financial_result.py  Resultado Financeiro (3.05)
  earnings.py          Lucro Líquido (3.11) TTM
  ebit.py              EBIT (3.05 + 3.06 net of financial result)
  ebt.py               EBT (Earnings Before Tax)
  revenue.py           Receita Líquida (3.01) TTM
  tax.py               Tributos sobre o lucro (3.10)
"""
