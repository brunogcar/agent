"""skills/cvm/calculations/engines/dva/ -- DVA (Demonstração do Valor
Adicionado / Value Added Statement) engines.

All DVA engines live in this subfolder. The `dva_` prefix was dropped from
file names because the subfolder provides the namespace (no collision with
DRE `revenue.py`, BPA `cash.py`, etc.).

ENGINE NAMING
-------------
- Generation-side engines (7.01-7.07) use `va_` prefix in their REGISTERED
  NAME (e.g., `va_revenue`, `va_inputs`) to avoid collision in the global
  ENGINES dict with DRE/BPA/BPP engines. The file name drops the prefix
  (e.g., `revenue.py`) since the subfolder provides namespace isolation.
- Distribution-side engines (7.08/8.x) keep their generic names
  (`value_added`, `total_tax`, `interest_paid`, `dividends_paid`) — they
  don't collide with anything.

GENERATION SIDE (wealth creation):
  revenue.py        (7.01)  Receitas
  inputs.py         (7.03)  Insumos Adquiridos de Terceiros
  gross_va.py       (7.04)  Valor Adicionado Bruto
  retentions.py     (7.05)  Retenções
  net_va.py         (7.06)  Valor Adicionado Líquido Produzido
  va_received.py    (7.07)  VA Recebido em Transferência

DISTRIBUTION SIDE (wealth distribution):
  value_added.py    (7.08/7.10) Total a Distribuir / Total a Adicionar
  total_tax.py      (8.2)       Tributos
  interest_paid.py  (8.3)       Juros suportados
  dividends_paid.py (7.08.04)   Dividendos + JCP

GENERATION IDENTITY:
  Revenues (7.01) - Inputs (7.03) = Gross Value Added (7.04)
  + Retentions (7.05) = Net Value Added Produced (7.06)
  + VA Received in Transfer (7.07) = Total VA to Distribute (7.08)

Auto-discovery is handled by _registry.py which globs engines/**/*.py
(including this subfolder).
"""
