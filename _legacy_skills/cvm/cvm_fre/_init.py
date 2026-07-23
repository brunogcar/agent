"""
skills/cvm/cvm_fre/__init__.py
Deploy to: D:\\mcp\\agent\\skills\\cvm\\cvm_fre\\__init__.py

Routes skill(domain="cvm", sub_domain="cvm_fre", mode=...) calls.

FRE = Formulario de Referencia (Annual Reference Form).
Filed by all listed companies. Covers governance, shareholder structure,
executive compensation, capital structure, auditors, board composition, etc.

=== WHAT YOU CAN QUERY ===
  documentos           - filing index: who filed, when, download link
  posicao_acionaria    - named shareholder stakes (% ON/PN/Total)
  distribuicao_capital - free float %, retail/institutional investor counts
  remuneracao_orgao    - board/exec compensation by governing body
  capital_social       - subscribed/paid-in capital + share counts

=== JOIN PATTERN ===
All section tables join to documentos via id_documento = documentos.id_doc.
Both tables carry cnpj for direct filtering without a join when needed.
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "cvm_fre",
    "description": (
        "CVM FRE (Formulario de Referencia) annual disclosure data. "
        "Shareholder structure, free float, board compensation, capital. "
        "5 structured tables per year from 2010+. "
        "Accepts B3 ticker, name fragment, or CNPJ."
    ),
    "source":  "dados.cvm.gov.br FRE ZIPs -> fre.db",
    "storage": "memory_db/cvm/fre.db",
    "modes": {
        "sync": {
            "description": (
                "Download CVM FRE ZIPs and populate fre.db. "
                "Default: current + prior year (~30-60s, 15-50MB/year). "
                "full_history=true: all years from 2010 (~15-20 min, ~500MB+)."
            ),
            "include_in_all": False,  # Too large for batch; always explicit
            "params": {
                "years":        "list[int]. Specific years. Default: current + prior.",
                "full_history": "bool. All years from 2010. Default: false.",
                "force":        "bool. Re-download even if synced. Default: false.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_fre", mode="sync")',
                'skill(domain="cvm", sub_domain="cvm_fre", mode="sync", params=\'{"years":[2023,2024]}\')',
            ],
        },
        "status": {
            "description": (
                "Show fre.db stats: row counts per table, synced years, date range."
            ),
            "include_in_all": True,
            "params": {},
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_fre", mode="status")',
            ],
        },
        "query": {
            "description": (
                "Query FRE data for a company. Select which section table to read. "
                "Sections: documentos (default), posicao_acionaria, "
                "distribuicao_capital, remuneracao_orgao, capital_social."
            ),
            "include_in_all": False,
            "params": {
                "company":   "str. B3 ticker (PETR4), name fragment, or CNPJ. Optional.",
                "section":   (
                    "str. Table to query. Options: documentos | posicao_acionaria | "
                    "distribuicao_capital | remuneracao_orgao | capital_social. "
                    "Default: documentos."
                ),
                "data_from": "str. Start date YYYY-MM-DD. Optional.",
                "data_to":   "str. End date YYYY-MM-DD. Optional.",
                "limit":     "int. Max results. Default: 20.",
                "cd_cvm":    "int. Direct CD_CVM lookup. Optional.",
            },
            "examples": [
                'skill(domain="cvm", sub_domain="cvm_fre", mode="query", params=\'{"company":"PETR4","section":"posicao_acionaria"}\')',
                'skill(domain="cvm", sub_domain="cvm_fre", mode="query", params=\'{"company":"VALE3","section":"remuneracao_orgao","data_from":"2023-01-01"}\')',
                'skill(domain="cvm", sub_domain="cvm_fre", mode="query", params=\'{"company":"ITUB4","section":"distribuicao_capital"}\')',
                'skill(domain="cvm", sub_domain="cvm_fre", mode="query", params=\'{"company":"PETR4","section":"capital_social"}\')',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """
    Dispatch cvm_fre mode call. Lazy imports for fast MCP server startup.
    Pattern identical to cvm_ipe/__init__.py -- keeps all skill dispatchers uniform.
    """
    if not mode:
        return {
            "status": "error",
            "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}",
        }
    if mode not in MANIFEST["modes"]:
        return {
            "status": "error",
            "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}",
        }
    try:
        if mode == "sync":
            from skills.cvm.cvm_fre_sync import sync as _fn
        elif mode == "status":
            from skills.cvm.cvm_fre_sync import status as _fn
        elif mode == "query":
            from skills.cvm.cvm_fre_sync import query as _fn
        else:
            return {"status": "error", "error": f"Unhandled mode '{mode}'"}

        # Filter kwargs to only what the function actually accepts
        # This prevents unexpected-keyword-argument errors when dispatcher
        # passes extra kwargs that a given function doesn't use
        sig      = inspect.signature(_fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return _fn(**filtered)

    except Exception as e:
        import traceback
        return {
            "status":    "error",
            "sub_domain": "cvm_fre",
            "mode":      mode,
            "error":     str(e),
            "traceback": traceback.format_exc(),
        }
