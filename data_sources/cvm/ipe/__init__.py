"""data_sources/cvm/ipe/__init__.py -- IPE sub-domain manifest and router.

IPE = Informações Periódicas e Eventuais (material events index).
Every time a company files a material event with CVM (earnings release,
dividend announcement, board change, M&A, etc.) it appears here.

This is the EVENT INDEX — not the document content itself. Link_Download
points to the actual PDF/XML on CVM's servers.

Data source: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/
Storage: memory_db/cvm/ipe.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "ipe",
    "description": (
        "CVM IPE material events index (Informações Periódicas e Eventuais). "
        "Earnings releases, dividend announcements, board changes, M&A. "
        "Single table (eventos) with metadata + download link."
    ),
    "source":  "dados.cvm.gov.br IPE ZIPs -> ipe.db",
    "storage": "memory_db/cvm/ipe.db",
    "modes": {
        "sync": {
            "description": "Download CVM IPE ZIPs and populate ipe.db. Default: current year.",
            "include_in_all": True,
            "params": {
                "years":        "list[int]. Specific years. Default: current year.",
                "full_history": "bool. All years from 2003. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="ipe", mode="sync")',
                'data_source(domain="cvm", sub_domain="ipe", mode="sync", params=\'{"years":[2024]}\')',
            ],
        },
        "status": {
            "description": "Show ipe.db stats: event count, year range, top categories.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="ipe", mode="status")',
            ],
        },
        "query": {
            "description": "Query IPE events by company, category, keyword, or date range.",
            "include_in_all": False,
            "params": {
                "company":   "str. Company name fragment, CNPJ, or B3 ticker.",
                "categoria": "str. Filter by category.",
                "tipo":      "str. Filter by type.",
                "keyword":   "str. Filter by keyword in assunto (subject).",
                "data_from": "str. Start date YYYY-MM-DD.",
                "data_to":   "str. End date YYYY-MM-DD.",
                "limit":     "int. Max results. Default: 20.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="ipe", mode="query", params=\'{"company":"PETR4"}\')',
                'data_source(domain="cvm", sub_domain="ipe", mode="query", params=\'{"keyword":"dividendo","data_from":"2024-01-01"}\')',
            ],
        },
        "search": {
            "description": "Search companies by name in the IPE database.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="ipe", mode="search", params=\'{"query":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch ipe mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.cvm.ipe.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.cvm.ipe.status_reporter import status as _status
            return _status()

        elif mode == "query":
            from data_sources.cvm.ipe.query_engine import query as _query
            sig = inspect.signature(_query)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _query(**filtered)

        elif mode == "search":
            from data_sources.cvm.ipe.query_engine import search as _search
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
            "sub_domain": "ipe",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
