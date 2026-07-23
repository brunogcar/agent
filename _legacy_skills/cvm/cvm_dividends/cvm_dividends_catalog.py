"""
skills/cvm/cvm_dividends/cvm_dividends_catalog.py -- Account codes for dividend data.

SOURCE: Empirical inspection of dfp_itr.db (12.5M rows in contas).
All codes verified present in >10,000 companies.

THREE DIVIDEND DATA LAYERS IN dfp_itr.db
----------------------------------------

Layer 1 -- DVA (Demonstração do Valor Adicionado)
  Total dividends + JCP distributed to shareholders per fiscal year.
  Available for ~10,139 companies. Most complete source.
  Key codes under 7.08.04 (Remuneração de Capitais Próprios):
    7.08.04.02  Dividendos
    7.08.04.03  Juros sobre Capital Próprio (JCP)
    7.08.04.01  Lucros Retidos / Prejuízos do Exercício (retained earnings)
    7.08.04     Remuneração de Capitais Próprios (subtotal)

Layer 2 -- BPP (Balance Sheet Liabilities)
  Dividends declared but not yet paid (as of balance sheet date).
  Also includes dividend reserves and proposed additional dividends.
    2.01.05.02.01  Dividendos e JCP a Pagar (current liability)
    2.01.05.02.02  Dividendo Mínimo Obrigatório a Pagar
    2.03.04.06     Reserva Especial para Dividendos Não Distribuídos
    2.03.04.08     Dividendo Adicional Proposto

Layer 3 -- DFC (Cash Flow Statement)
  Actual cash paid for dividends and JCP during the period.
  Multiple code variants exist across companies (different layouts).
    6.03.01  Dividendos e JCP Pagos (variant A)
    6.03.02  Dividendos e JCP Pagos (variant B)
    6.03.03  Dividendos e JCP Pagos (variant C)

DECISION: DVA is the primary source because:
  - Covers ~10,139 companies vs ~100 for DFC dividend-specific codes
  - Directly shows what was DISTRIBUTED to shareholders (total remuneration)
  - Splits Dividendos vs JCP clearly
  - Available for both annual (meses=12) and quarterly (meses=3/6/9)
  DFC is secondary -- useful for cash-basis confirmation per company.
  BPP is tertiary -- shows declared-but-unpaid and reserves at period end.

JCP NOTE: Juros sobre Capital Próprio is a Brazilian tax mechanism where
companies pay interest on equity to shareholders as a tax-deductible expense.
Economically equivalent to dividends but treated differently for tax purposes.
Both DVA 7.08.04.02 (Dividendos) and 7.08.04.03 (JCP) should be summed
for total shareholder cash remuneration.

MESES NOTE: DVA quarterly (meses=3/6/9) values are CUMULATIVE within the year.
Annual (meses=12) is the definitive full-year figure.
"""

from __future__ import annotations
from pathlib import Path
from core.config import cfg

# Database path -- same dfp_itr.db used by cvm_dfp_itr
dfp_itr_DB = cfg.memory_root / "cvm" / "dfp_itr.db"

# ---------------------------------------------------------------------------
# DVA dividend codes (primary source)
# ---------------------------------------------------------------------------

DVA_DIVIDEND_CODES: dict[str, str] = {
    "7.08.04":    "Remuneração de Capitais Próprios (subtotal)",
    "7.08.04.01": "Lucros Retidos / Prejuízos do Exercício",
    "7.08.04.02": "Dividendos",
    "7.08.04.03": "Juros sobre Capital Próprio (JCP)",
    "7.08.04.04": "Dividendo Mínimo Obrigatório",
    "7.08.04.05": "Dividendo Adicional Proposto",
}

# For the resumo view -- the key codes
DVA_KEY_CODES = ["7.08.04", "7.08.04.02", "7.08.04.03"]

# ---------------------------------------------------------------------------
# BPP dividend codes (declared/payable)
# ---------------------------------------------------------------------------

BPP_DIVIDEND_CODES: dict[str, str] = {
    "2.01.05.02.01": "Dividendos e JCP a Pagar",
    "2.01.05.02.02": "Dividendo Mínimo Obrigatório a Pagar",
    "2.03.04.06":    "Reserva Especial para Dividendos Não Distribuídos",
    "2.03.04.08":    "Dividendo Adicional Proposto",
}

# ---------------------------------------------------------------------------
# DFC dividend codes (cash paid -- multiple variants across companies)
# ---------------------------------------------------------------------------

DFC_DIVIDEND_CODES: dict[str, str] = {
    "6.03.01": "Dividendos e JCP Pagos",
    "6.03.02": "Dividendos e JCP Pagos",
    "6.03.03": "Dividendos e JCP Pagos",
}

# All DFC codes to search -- UNION across variants
DFC_CODE_LIST = list(DFC_DIVIDEND_CODES.keys())

# ---------------------------------------------------------------------------
# Label maps for output formatting
# ---------------------------------------------------------------------------

CODE_LABELS: dict[str, str] = {
    **DVA_DIVIDEND_CODES,
    **BPP_DIVIDEND_CODES,
    **DFC_DIVIDEND_CODES,
}

def get_label(codigo: str, descr: str = "") -> str:
    """Return canonical label for a code, falling back to descr from DB."""
    return CODE_LABELS.get(codigo, descr)
