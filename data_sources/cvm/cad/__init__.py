"""data_sources/cvm/cad/__init__.py -- CAD sub-domain manifest and router.

CAD = Cadastro de Companhias Abertas (company register).
A single CSV file (~1.5MB, ~3500 companies) updated weekly by CVM.

This is the BRIDGE data source — CD_CVM links to DFP/ITR/FRE filings,
CNPJ links to B3 instruments. Primary use case: company resolution
(ticker → CNPJ → CD_CVM → financial statements).

Data source: https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
Storage: memory_db/cvm/cad.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "cad",
    "description": (
        "CVM company register (Cadastro de Companhias Abertas). "
        "~3500 companies with CNPJ, CD_CVM, names, status, sector. "
        "Primary use: company resolution (ticker → CNPJ → CD_CVM → financials)."
    ),
    "source":  "dados.cvm.gov.br/cad_cia_aberta.csv -> cad.db",
    "storage": "memory_db/cvm/cad.db",
    "modes": {
        "sync": {
            "description": "Download cad_cia_aberta.csv and populate cad.db. Full replace (~1.5MB, ~2s).",
            "include_in_all": True,
            "params": {
                "force": "bool. Re-download even if already synced today. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="cad", mode="sync")',
                'data_source(domain="cvm", sub_domain="cad", mode="sync", params=\'{"force":true}\')',
            ],
        },
        "status": {
            "description": "Show cad.db stats: total/active/cancelled companies, last sync, top sectors.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="cad", mode="status")',
            ],
        },
        "lookup": {
            "description": "Look up a single company by CNPJ, CD_CVM, or name. Returns best match.",
            "include_in_all": False,
            "params": {
                "cnpj":   "str. Company CNPJ (formatted or numeric).",
                "cd_cvm": "str. CVM internal code (e.g., '9512').",
                "name":   "str. Company name or fragment.",
                "full":   "bool. Return all 46 columns. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="cad", mode="lookup", params=\'{"cnpj":"33000167000101"}\')',
                'data_source(domain="cvm", sub_domain="cad", mode="lookup", params=\'{"name":"PETROBRAS"}\')',
                'data_source(domain="cvm", sub_domain="cad", mode="lookup", params=\'{"cd_cvm":"9512"}\')',
            ],
        },
        "search": {
            "description": "Search companies with filters (name, sector, status, control type, UF).",
            "include_in_all": False,
            "params": {
                "name":        "str. Name fragment.",
                "setor":       "str. Sector fragment.",
                "sit":         "str. Registration status (ATIVO, CANCELADA).",
                "controle":    "str. Control type (PRIVADO, ESTATAL).",
                "uf":          "str. State code (SP, RJ, MG).",
                "active_only": "bool. Default true.",
                "limit":       "int. Max results. Default: 20.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="cad", mode="search", params=\'{"setor":"Energia"}\')',
                'data_source(domain="cvm", sub_domain="cad", mode="search", params=\'{"controle":"ESTATAL"}\')',
            ],
        },
        "sectors": {
            "description": "List all distinct sectors (SETOR_ATIV) with company counts.",
            "include_in_all": False,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="cad", mode="sectors")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch cad mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.cvm.cad.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.cvm.cad.status_reporter import status as _status
            return _status()

        elif mode == "lookup":
            from data_sources.cvm.cad.query_engine import lookup as _lookup
            sig = inspect.signature(_lookup)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _lookup(**filtered)

        elif mode == "search":
            from data_sources.cvm.cad.query_engine import search as _search
            sig = inspect.signature(_search)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _search(**filtered)

        elif mode == "sectors":
            from data_sources.cvm.cad.query_engine import sectors as _sectors
            return _sectors()

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "cad",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
