"""data_sources/cvm/dfp/__init__.py -- DFP sub-domain manifest and router.

DFP = Demonstrações Financeiras Padronizadas (annual financial statements).
Filed once per year. Contains BPA, BPP, DRE, DFC, DVA, DMPL.

Data source: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/
Storage: memory_db/cvm/dfp.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "dfp",
    "description": (
        "CVM DFP annual financial statements (BPA, BPP, DRE, DFC, DVA, DMPL). "
        "Annual filings from 2010-present. Query by ticker, name, or CNPJ."
    ),
    "source":  "dados.cvm.gov.br DFP ZIPs -> dfp.db",
    "storage": "memory_db/cvm/dfp.db",
    "modes": {
        "sync": {
            "description": (
                "Download CVM DFP ZIPs and populate dfp.db. "
                "Default: current year only (~30s). full_history=true: all years 2010-present (~10 min)."
            ),
            "include_in_all": True,
            "params": {
                "years":        "list[int]. Specific years. Default: current year.",
                "full_history": "bool. All years from 2010. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="dfp", mode="sync")',
                'data_source(domain="cvm", sub_domain="dfp", mode="sync", params=\'{"years":[2023,2024]}\')',
                'data_source(domain="cvm", sub_domain="dfp", mode="sync", params=\'{"full_history":true}\')',
            ],
        },
        "status": {
            "description": "Show dfp.db stats: empresas, contas, date range, synced years, group breakdown.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="dfp", mode="status")',
            ],
        },
        "query": {
            "description": "Full annual statements for a company (all account codes, all groups).",
            "include_in_all": False,
            "params": {
                "company":     "str. B3 ticker, name fragment, or CNPJ. Required.",
                "grupo":       "str. BPA|BPP|DRE|DFC_MI|DFC_MD|DVA|DMPL. Optional.",
                "codigo":      "str. Account code prefix e.g. '1.01'. Optional.",
                "anos":        "list[int]. Specific years. Default: last 5.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="dfp", mode="query", params=\'{"company":"PETR4"}\')',
                'data_source(domain="cvm", sub_domain="dfp", mode="query", params=\'{"company":"VALE3","grupo":"DRE"}\')',
            ],
        },
        "resumo": {
            "description": "Summary annual metrics (key accounts: Ativo Total, Receita, Lucro, EBIT, etc.).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
                "anos":    "list[int]. Default: last 10.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="dfp", mode="resumo", params=\'{"company":"ITUB4"}\')',
            ],
        },
        "search": {
            "description": "Search companies by name fragment. Returns matches with CNPJ + available years.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="dfp", mode="search", params=\'{"query":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch dfp mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.cvm.dfp.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.cvm.dfp.status_reporter import status as _status
            return _status()

        elif mode == "query":
            from data_sources.cvm.dfp.query_engine import query as _query
            sig = inspect.signature(_query)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _query(**filtered)

        elif mode == "resumo":
            from data_sources.cvm.dfp.query_engine import resumo as _resumo
            sig = inspect.signature(_resumo)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _resumo(**filtered)

        elif mode == "search":
            from data_sources.cvm.dfp.query_engine import search as _search
            sig = inspect.signature(_search)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _search(**filtered)

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "dfp",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
