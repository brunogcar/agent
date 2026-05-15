"""
skills/cvm/cvm_register/__init__.py -- CVM Register sub-domain manifest.

Routes skill(domain="cvm", sub_domain="cvm_register", mode=...) calls.
Reads from register.db (built from cad_cia_aberta.csv).
"""

from __future__ import annotations
import inspect
from skills.cvm.cvm_register.cvm_register import (
    sync, lookup, search, sectors, db_status,
)

MANIFEST = {
    "sub_domain":  "cvm_register",
    "description": "CVM company register (cad_cia_aberta.csv). Lookup/search ~3,500 companies. Key: CD_CVM links all CVM filings, CNPJ_CIA links B3 data.",
    "source":      "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
    "storage":     "memory_db/cvm/register.db (~5MB, updated weekly)",

    "modes": {
        "sync": {
            "fn":             sync,
            "description":    "Download cad_cia_aberta.csv and store to register.db.",
            "include_in_all": True,
            "params": {
                "force": "bool. Re-download even if synced today. Default: False.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_register", mode="sync")',
                'skill(domain="cvm", sub_domain="cvm_register", mode="sync", params=\'{"force":true}\')',
            ],
        },
        "lookup": {
            "fn":             lookup,
            "description":    "Find one company by CNPJ, CD_CVM, or name. Returns CD_CVM + CNPJ_CIA for linking.",
            "include_in_all": False,
            "params": {
                "cnpj":   "str. CNPJ formatted or numeric.",
                "cd_cvm": "str. CVM internal code e.g. '9512'.",
                "name":   "str. Name fragment.",
                "full":   "bool. Return all 46 columns. Default: False.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_register", mode="lookup", params=\'{"name":"PETROBRAS"}\')',
                'skill(domain="cvm", sub_domain="cvm_register", mode="lookup", params=\'{"cnpj":"33.000.167/0001-01"}\')',
                'skill(domain="cvm", sub_domain="cvm_register", mode="lookup", params=\'{"cd_cvm":"9512"}\')',
            ],
        },
        "search": {
            "fn":             search,
            "description":    "Search companies with filters: sector, status, state, ownership.",
            "include_in_all": False,
            "params": {
                "name":        "str. Name fragment.",
                "setor":       "str. Sector e.g. 'Energia', 'Petróleo', 'Bancos'.",
                "sit":         "str. Status: 'ATIVO', 'CANCELADA'.",
                "sit_emissor": "str. Issuer situation fragment.",
                "controle":    "str. Ownership: 'PRIVADO', 'ESTATAL', 'ESTRANGEIRO'.",
                "uf":          "str. State: 'SP', 'RJ', 'MG'.",
                "active_only": "bool. Only SIT=ATIVO. Default: True.",
                "limit":       "int. Max results. Default: 20.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_register", mode="search", params=\'{"setor":"Energia Elétrica"}\')',
                'skill(domain="cvm", sub_domain="cvm_register", mode="search", params=\'{"controle":"ESTATAL"}\')',
                'skill(domain="cvm", sub_domain="cvm_register", mode="search", params=\'{"setor":"Petróleo","uf":"RJ"}\')',
            ],
        },
        "sectors": {
            "fn":             sectors,
            "description":    "List all CVM activity sectors with company counts.",
            "include_in_all": False,
            "params":         {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_register", mode="sectors")',
            ],
        },
        "status": {
            "fn":             db_status,
            "description":    "Show register.db sync status and stats.",
            "include_in_all": True,
            "params":         {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_register", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    if not mode:
        return {"status": "error", "error": f"mode is required for cvm_register. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}' for cvm_register. Available: {list(MANIFEST['modes'].keys())}"}
    fn       = MANIFEST["modes"][mode]["fn"]
    sig      = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "sub_domain": "cvm_register", "mode": mode, "error": str(e)}
