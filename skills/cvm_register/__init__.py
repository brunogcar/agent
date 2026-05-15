"""
skills/cvm_register/__init__.py -- CVM company register domain manifest.

Routes skill(domain="cvm_register", mode=...) calls to cvm_register_api.py.

MODES
-----
  sync    -- download cad_cia_aberta.csv and store to register.db (~1.5MB, weekly)
  lookup  -- find one company by CNPJ, CD_CVM, or name
  search  -- filter companies by sector, status, state, ownership control
  sectors -- list all CVM sectors with company counts
  status  -- register.db file info

LINKING TO OTHER SKILLS
-----------------------
  cvm_register -> cvm:
    result["CNPJ_CIA"] == empresas.cnpj (after normalizing dots/slashes)
    Use lookup() to get CNPJ, then pass to cvm skill for financials

  cvm_register -> b3_api:
    result["CNPJ_CIA"] (numeric) == isin.cnpj in rapina.db
    CD_CVM links to all CVM filing datasets (DFP, ITR, FRE)

  cvm_register -> future FRE skill:
    CD_CVM is the primary key in all FRE CSV files
    CNPJ_CIA used as secondary key

IMPORTANT FIELDS
----------------
  CD_CVM          -- CVM internal code, links all CVM filings
  CNPJ_CIA        -- company CNPJ, links to rapina.db and B3 data
  DENOM_COMERC    -- commercial name (what people call the company)
  DENOM_SOCIAL    -- legal name (in formal documents)
  SETOR_ATIV      -- activity sector (CVM classification)
  SIT             -- registration status: ATIVO | CANCELADA | SUSPENSO
  SIT_EMISSOR     -- issuer situation (more detailed than SIT)
  CONTROLE_ACIONARIO -- PRIVADO | ESTATAL | ESTRANGEIRO | COOPERATIVA
  CATEG_REG       -- registration category: Categoria A | Categoria B
"""

from __future__ import annotations
import inspect

from skills.cvm_register.cvm_register_api import (
    sync,
    lookup,
    search,
    sectors,
    db_status,
)


MANIFEST: dict = {
    "domain":      "cvm_register",
    "description": (
        "CVM company register (cad_cia_aberta.csv). "
        "Lookup and search ~3,500 companies registered with Brazil's CVM. "
        "Key identifiers: CD_CVM (links all CVM filings), CNPJ_CIA (links B3 and rapina.db)."
    ),
    "source":  "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
    "storage": "memory_db/cvm/register.db (SQLite, ~5MB, updated weekly)",

    "modes": {

        "sync": {
            "fn":          sync,
            "description": "Download cad_cia_aberta.csv from CVM and store to register.db. "
                           "Safe to re-run (skips if already synced today).",
            "params": {
                "force": "bool. Re-download even if synced today. Default: False.",
            },
            "examples": [
                'skill(domain="cvm_register", mode="sync")',
                'skill(domain="cvm_register", mode="sync", force=True)',
            ],
        },

        "lookup": {
            "fn":          lookup,
            "description": "Find one company by CNPJ, CD_CVM, or name. "
                           "Returns CD_CVM and CNPJ_CIA for linking to other skills.",
            "params": {
                "cnpj":   "str. Company CNPJ, formatted or numeric. e.g. '33.000.167/0001-01'",
                "cd_cvm": "str. CVM internal code. e.g. '9512'",
                "name":   "str. Company name or fragment. Searches legal and commercial name.",
                "full":   "bool. Return all 46 columns. Default: False (key fields only).",
            },
            "examples": [
                'skill(domain="cvm_register", mode="lookup", name="PETROBRAS")',
                'skill(domain="cvm_register", mode="lookup", cnpj="33.000.167/0001-01")',
                'skill(domain="cvm_register", mode="lookup", cd_cvm="9512")',
                'skill(domain="cvm_register", mode="lookup", name="VALE", full=True)',
            ],
        },

        "search": {
            "fn":          search,
            "description": "Search companies with multiple filters. Returns a list. "
                           "Default: active companies only (SIT=ATIVO).",
            "params": {
                "name":        "str. Company name fragment.",
                "setor":       "str. Sector fragment. e.g. 'Energia', 'Petróleo', 'Bancos'.",
                "sit":         "str. Registration status. e.g. 'ATIVO', 'CANCELADA'.",
                "sit_emissor": "str. Issuer situation fragment. e.g. 'RECUPERACAO'.",
                "controle":    "str. Ownership control. e.g. 'PRIVADO', 'ESTATAL', 'ESTRANGEIRO'.",
                "uf":          "str. State code. e.g. 'SP', 'RJ', 'MG'.",
                "active_only": "bool. Filter to SIT=ATIVO only. Default: True.",
                "limit":       "int. Max results. Default: 20.",
            },
            "examples": [
                'skill(domain="cvm_register", mode="search", setor="Energia Elétrica")',
                'skill(domain="cvm_register", mode="search", setor="Petróleo", uf="RJ")',
                'skill(domain="cvm_register", mode="search", controle="ESTATAL")',
                'skill(domain="cvm_register", mode="search", sit_emissor="RECUPERACAO")',
                'skill(domain="cvm_register", mode="search", name="BANCO", uf="SP", limit=10)',
                'skill(domain="cvm_register", mode="search", active_only=False, sit="CANCELADA", limit=5)',
            ],
        },

        "sectors": {
            "fn":          sectors,
            "description": "List all CVM activity sectors with company counts. "
                           "Use sector names from here as input to search(setor=...).",
            "params": {},
            "examples": [
                'skill(domain="cvm_register", mode="sectors")',
            ],
        },

        "status": {
            "fn":          db_status,
            "description": "Show register.db sync status: size, row counts, last update.",
            "params": {},
            "examples": [
                'skill(domain="cvm_register", mode="status")',
            ],
        },
    },
}


def route(mode: str, **kwargs) -> dict:
    """
    Route skill(domain='cvm_register', mode=...) to the correct function.
    Uses inspect.signature to filter kwargs -- same pattern as cvm and b3_api.
    """
    if mode not in MANIFEST["modes"]:
        return {
            "status": "error",
            "error":  f"Unknown mode '{mode}' for domain 'cvm_register'. "
                      f"Available: {list(MANIFEST['modes'].keys())}",
        }

    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {
            "status": "error",
            "domain": "cvm_register",
            "mode":   mode,
            "error":  str(e),
        }
