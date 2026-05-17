"""
skills/cvm/cvm_shareholders/cvm_shareholders_catalog.py -- Account codes for shareholder data.

SOURCE: Empirical inspection of rapina.db (12.5M rows in contas).

SHAREHOLDER DATA IN rapina.db
------------------------------
All shareholder data comes from BPP (Balanço Patrimonial Passivo)
under the Patrimônio Líquido (Equity) section, codigo 2.03.*.

rapina.db does NOT contain:
  - Individual shareholder names or ownership percentages (that's FRE data)
  - Share counts by class (that's FRE data)

rapina.db DOES contain:
  - Total equity and its breakdown (capital, reserves, retained earnings)
  - Minority interest (non-controlling shareholders) value
  - Capital structure evolution over time
  - Equity per component for any of ~10,800 companies

EQUITY STRUCTURE (BPP 2.03.*)
------------------------------
2.03        Patrimônio Líquido (Consolidado)  -- Total equity
2.03.01     Capital Social Realizado           -- Paid-in capital
2.03.02     Reservas de Capital                -- Capital reserves
2.03.03     Reservas de Reavaliação            -- Revaluation reserves (rare)
2.03.04     Reservas de Lucros                 -- Profit reserves
  2.03.04.01  Reserva Legal
  2.03.04.02  Reserva Estatutária
  2.03.04.03  Reserva para Contingências
  2.03.04.04  Reserva de Incentivos Fiscais
  2.03.04.05  Reserva de Retenção de Lucros
  2.03.04.06  Reserva Especial p/ Dividendos Não Distribuídos
  2.03.04.07  Reserva de Equalização de Dividendos
  2.03.04.08  Dividendo Adicional Proposto
2.03.05     Lucros/Prejuízos Acumulados        -- Retained earnings / accumulated losses
2.03.06     Ajustes de Avaliação Patrimonial   -- OCI (Other comprehensive income)
2.03.07     Ajustes Acumulados de Conversão    -- Currency translation adjustment
2.03.08     Outros Resultados Abrangentes      -- Other comprehensive income
2.03.09     Participação dos Acionistas Não Controladores -- Minority interest

MINORITY INTEREST NOTE (2.03.09)
---------------------------------
Present in ~5,931 companies (consolidated statements with subsidiaries).
Represents the equity of non-controlling shareholders in subsidiaries.
The remainder (2.03 minus 2.03.09) is attributable to the parent company shareholders.
This is the only shareholder-split data available in rapina.db without FRE.

DECISION: Focus on equity structure + minority interest as the core shareholder
data available. Full ownership % requires FRE filings (future cvm_fre skill).
"""

from __future__ import annotations
from pathlib import Path
from core.config import cfg

RAPINA_DB = cfg.memory_root / "cvm" / "rapina.db"

# ---------------------------------------------------------------------------
# Equity structure codes (BPP 2.03.*)
# ---------------------------------------------------------------------------

EQUITY_CODES: dict[str, str] = {
    "2.03":       "Patrimônio Líquido Total",
    "2.03.01":    "Capital Social Realizado",
    "2.03.02":    "Reservas de Capital",
    "2.03.03":    "Reservas de Reavaliação",
    "2.03.04":    "Reservas de Lucros",
    "2.03.04.01": "Reserva Legal",
    "2.03.04.02": "Reserva Estatutária",
    "2.03.04.05": "Reserva de Retenção de Lucros",
    "2.03.04.06": "Reserva Especial p/ Dividendos Não Distribuídos",
    "2.03.04.08": "Dividendo Adicional Proposto",
    "2.03.05":    "Lucros/Prejuízos Acumulados",
    "2.03.06":    "Ajustes de Avaliação Patrimonial",
    "2.03.07":    "Ajustes Acumulados de Conversão",
    "2.03.08":    "Outros Resultados Abrangentes",
    "2.03.09":    "Participação dos Acionistas Não Controladores (Minority Interest)",
}

# Top-level codes for the summary view
EQUITY_SUMMARY_CODES = [
    "2.03", "2.03.01", "2.03.02", "2.03.04",
    "2.03.05", "2.03.06", "2.03.09",
]

# Full detail codes
EQUITY_ALL_CODES = list(EQUITY_CODES.keys())

def get_label(codigo: str, descr: str = "") -> str:
    return EQUITY_CODES.get(codigo, descr)
