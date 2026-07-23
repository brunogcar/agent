"""data_sources/cvm/itr/catalog.py -- Schema constants for ITR (quarterly filings).

CVM ITR (Informações Trimestrais) = quarterly financial statements.
Filed 3x per year (Q1, H1, 9M — cumulative). Contains the same statement
groups as DFP (BPA, BPP, DRE, DFC, DVA, DMPL) but with meses=3/6/9.

ITR data is CUMULATIVE (Jan→Mar, Jan→Jun, Jan→Sep), NOT standalone quarters.
Standalone quarter computation (T2 = H1 − Q1, etc.) belongs in the skills/ layer.
"""

from __future__ import annotations

# Same statement groups as DFP
from data_sources.cvm.dfp.catalog import (
    GRUPOS, SNAPSHOT_GRUPOS, FLOW_GRUPOS,
    MESES_LABELS, CSV_COLUMNS, CSV_ENCODING, CSV_DELIMITER,
)

# URL pattern (ITR uses a different path)
CVM_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS"
URL_PATTERN = f"{CVM_BASE_URL}/itr_cia_aberta_{{year}}.zip"

# ITR data starts in 2015 (CVM started publishing ITR ZIPs from 2015)
FIRST_YEAR = 2015

# ITR meses values (cumulative quarters)
ITR_MESES = [3, 6, 9]

# Same RESUMO_ACCOUNTS as DFP (same chart of accounts)
from data_sources.cvm.dfp.catalog import RESUMO_ACCOUNTS, RESUMO_LOOKUP
