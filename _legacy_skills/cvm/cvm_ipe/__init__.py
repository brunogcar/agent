"""
skills/cvm/cvm_ipe/__init__.py
Deploy to: D:\mcp\agent\skills\cvm\cvm_ipe\__init__.py

Routes skill(domain="cvm", sub_domain="cvm_ipe", mode=...) calls.

IPE = Informacoes Periodicas e Eventuais (material events index).
Each row is a filing event with metadata and a download link.
The actual document content (PDF/XML) is at Link_Download.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "cvm_ipe",
    "description": (
        "CVM IPE material events index. Every filing, announcement, "
        "dividend notice, board change, M&A event for ~3K listed companies. "
        "2003-present. Accepts B3 ticker, name fragment, or CNPJ."
    ),
    "source":  "dados.cvm.gov.br IPE ZIPs -> ipe.db",
    "storage": "memory_db/cvm/ipe.db",
    "modes": {
        "sync": {
            "description": (
                "Download CVM IPE ZIPs and populate ipe.db. "
                "Default: current + prior year (~10s). "
                "full_history=true: all years from 2003 (~2-3 min)."
            ),
            "include_in_all": False,
            "params": {
                "years":        "list[int]. Specific years. Default: current + prior.",
                "full_history": "bool. All years from 2003. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="sync")',
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="sync", params=\'{"full_history":true}\')',
            ],
        },
        "status": {
            "description": "Show ipe.db stats: total events, date range, synced years, top categories.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="status")',
            ],
        },
        "query": {
            "description": (
                "Query IPE events for a company or by keyword/category. "
                "Returns event list with metadata and download links."
            ),
            "include_in_all": False,
            "params": {
                "company":   "str. B3 ticker (PETR4), name fragment, or CNPJ. Optional.",
                "categoria": "str. Category filter e.g. 'Comunicado ao Mercado'. Optional.",
                "tipo":      "str. Tipo filter e.g. 'Aviso aos Acionistas'. Optional.",
                "keyword":   "str. Keyword in assunto (subject). Optional.",
                "data_from": "str. Start date YYYY-MM-DD. Optional.",
                "data_to":   "str. End date YYYY-MM-DD. Optional.",
                "limit":     "int. Max results. Default: 20.",
                "cd_cvm":    "int. Direct CD_CVM lookup. Optional.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="query", params=\'{"company":"PETR4","keyword":"dividendo"}\')',
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="query", params=\'{"company":"VALE3","data_from":"2024-01-01"}\')',
                'skill(domain="cvm", sub_domain="cvm_ipe", mode="query", params=\'{"keyword":"aquisicao","data_from":"2024-01-01","limit":10}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch cvm_ipe mode call. Lazy imports for fast server startup."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}
    try:
        if mode == "sync":
            from skills.cvm.cvm_ipe_sync import sync as _fn
        elif mode == "status":
            from skills.cvm.cvm_ipe_sync import status as _fn
        elif mode == "query":
            from skills.cvm.cvm_ipe_sync import query as _fn

        sig      = inspect.signature(_fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return _fn(**filtered)

    except Exception as e:
        import traceback
        return {"status": "error", "sub_domain": "cvm_ipe", "mode": mode,
                "error": str(e), "traceback": traceback.format_exc()}