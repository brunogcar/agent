"""data_sources/cvm/fre/__init__.py -- FRE sub-domain manifest and router.

FRE = Formulário de Referência (annual reference form).
Corporate governance + ownership + compensation data.

Unlike DFP/ITR (financial statements), FRE has no meses/flow/snapshot concept.
It contains 5 tables: documentos, posicao_acionaria, distribuicao_capital,
remuneracao_orgao, capital_social.

Data source: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/
Storage: memory_db/cvm/fre.db
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "fre",
    "description": (
        "CVM FRE (Formulário de Referência) annual reference form. "
        "Corporate governance: shareholders, free float, executive compensation, "
        "stock capital. 5 tables from 50+ in the ZIP."
    ),
    "source":  "dados.cvm.gov.br FRE ZIPs -> fre.db",
    "storage": "memory_db/cvm/fre.db",
    "modes": {
        "sync": {
            "description": (
                "Download CVM FRE ZIPs and populate fre.db. "
                "Default: current year only. full_history=true: all years 2010-present."
            ),
            "include_in_all": True,
            "params": {
                "years":        "list[int]. Specific years. Default: current year.",
                "full_history": "bool. All years from 2010. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="sync")',
                'data_source(domain="cvm", sub_domain="fre", mode="sync", params=\'{"years":[2024]}\')',
            ],
        },
        "status": {
            "description": "Show fre.db stats: table row counts, year range, synced years.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="status")',
            ],
        },
        "shareholders": {
            "description": "Query shareholder composition (who owns the company, ownership %).",
            "include_in_all": False,
            "params": {
                "company": "str. B3 ticker, name fragment, or CNPJ. Required.",
                "limit":   "int. Max shareholders. Default: 50.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="shareholders", params=\'{"company":"PETR4"}\')',
            ],
        },
        "free_float": {
            "description": "Query free float / shareholder distribution (circulation %, shareholder counts).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="free_float", params=\'{"company":"VALE3"}\')',
            ],
        },
        "compensation": {
            "description": "Query executive/board compensation (salary, bonus, stock-based).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="compensation", params=\'{"company":"PETR4"}\')',
            ],
        },
        "capital": {
            "description": "Query stock capital + share counts (ON/PN/total, capital value).",
            "include_in_all": False,
            "params": {
                "company": "str. Required.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="capital", params=\'{"company":"PETR4"}\')',
            ],
        },
        "search": {
            "description": "Search companies by name fragment in the FRE database.",
            "include_in_all": False,
            "params": {
                "query": "str. Name fragment. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'data_source(domain="cvm", sub_domain="fre", mode="search", params=\'{"query":"PETROBRAS"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch fre mode call."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync":
            from data_sources.cvm.fre.sync_engine import sync as _sync
            sig = inspect.signature(_sync)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _sync(**filtered)

        elif mode == "status":
            from data_sources.cvm.fre.status_reporter import status as _status
            return _status()

        elif mode == "shareholders":
            from data_sources.cvm.fre.query_engine import shareholders as _fn
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        elif mode == "free_float":
            from data_sources.cvm.fre.query_engine import free_float as _fn
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        elif mode == "compensation":
            from data_sources.cvm.fre.query_engine import compensation as _fn
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        elif mode == "capital":
            from data_sources.cvm.fre.query_engine import capital as _fn
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        elif mode == "search":
            from data_sources.cvm.fre.query_engine import search as _fn
            sig = inspect.signature(_fn)
            filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
            return _fn(**filtered)

        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "fre",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
