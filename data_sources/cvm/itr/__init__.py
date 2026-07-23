"""data_sources/cvm/itr/__init__.py -- ITR sub-domain manifest and router.

ITR = Informações Trimestrais (quarterly financial statements).
Filed 3x per year (Q1, H1, 9M — cumulative periods).
Contains same statement groups as DFP but with meses=3/6/9.

Data source: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/
Storage: memory_db/cvm/itr.db

NOTE: ITR data is CUMULATIVE (Jan→Mar, Jan→Jun, Jan→Sep), NOT standalone
quarters. Standalone quarter computation (T2=H1−Q1, T3=9M−H1, T4=DFP−9M)
belongs in the skills/ layer, which combines ITR + DFP data.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "itr",
    "description": (
        "CVM ITR quarterly financial statements (cumulative: Q1, H1, 9M). "
        "Same statement groups as DFP but with meses=3/6/9. "
        "Data is CUMULATIVE, NOT standalone quarters."
    ),
    "source":  "dados.cvm.gov.br ITR ZIPs -> itr.db",
    "storage": "memory_db/cvm/itr.db",
    "modes": {
        "sync": {
            "description": (
                "Download CVM ITR ZIPs and populate itr.db. "
                "Default: current year only. full_history=true: all years 2015-present."
            ),
            "include_in_all": True,
            "params": {
                "years":        "list[int]. Specific years. Default: current year.",
                "full_history": "bool. All years from 2015. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="itr", mode="sync")',
                'data_source(domain="cvm", sub_domain="itr", mode="sync", params=\'{"years":[2024]}\')',
            ],
        },
        "status": {
            "description": "Show itr.db stats: empresas, contas, date range, synced years, meses distribution.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="itr", mode="status")',
            ],
        },
        "query": {
            "description": "Full quarterly statements for a company (all account codes, cumulative).",
            "include_in_all": False,
            "params": {
                "company":     "str. B3 ticker, name fragment, or CNPJ. Required.",
                "grupo":       "str. BPA|BPP|DRE|DFC_MI|DFC_MD|DVA|DMPL. Optional.",
                "codigo":      "str. Account code prefix. Optional.",
                "anos":        "list[int]. Specific years. Default: last 3.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="itr", mode="query", params=\'{"company":"PETR4"}\')',
            ],
        },
        "resumo": {
            "description": "Summary quarterly metrics (key accounts, cumulative).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
                "anos":    "list[int]. Default: last 3.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="itr", mode="resumo", params=\'{"company":"PETR4"}\')',
            ],
        },
        "search": {
            "description": "Search companies by name fragment in the ITR database.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="itr", mode="search", params=\'{"query":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch itr mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.cvm.itr.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.cvm.itr.status_reporter import status as _status
            return _status()

        elif mode == "query":
            from data_sources.cvm.itr.query_engine import query as _query
            sig = inspect.signature(_query)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _query(**filtered)

        elif mode == "resumo":
            from data_sources.cvm.itr.query_engine import resumo as _resumo
            sig = inspect.signature(_resumo)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _resumo(**filtered)

        elif mode == "search":
            from data_sources.cvm.itr.query_engine import search as _search
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
            "sub_domain": "itr",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
