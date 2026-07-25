"""data_sources/cvm/fca/__init__.py -- FCA (Formulário Cadastral) data source manifest.

FCA = Formulário Cadastral. Contains company registration data + listed
securities (including ticker -> CNPJ mapping + listing segment).

Three tables synced (the valuable ones):
  fca_geral             -- company registration (complements CAD: fiscal year end,
                           web page, control type, registration category, activity)
  fca_valor_mobiliario  -- listed securities (Codigo_Negociacao/ticker -> CNPJ,
                           listing segment: Novo Mercado/Nível 1/Nível 2, etc.)
  fca_pais_estrangeiro  -- foreign listings (ADR/foreign exchange listings like
                           VALE/PETR4 on NYSE/Nasdaq)

URL pattern:
  http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_YYYY.zip

Each ZIP contains 9 CSVs. We sync only the 3 valuable ones (skip contact info).
"""

from __future__ import annotations

MANIFEST = {
    "sub_domain": "fca",
    "description": (
        "FCA — Formulário Cadastral (registration form). "
        "sync: download annual ZIPs from CVM. "
        "query: company registration + listed securities (ticker -> CNPJ). "
        "status: sync statistics."
    ),
    "source": "CVM FCA API (http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/)",
    "storage": "SQLite — fca.db",
    "has_sub_domains": False,
    "modes": {
        "sync":   "Download + parse FCA ZIPs from CVM into fca.db.",
        "query":  "Query company registration + listed securities by ticker/CNPJ/CVM.",
        "status": "Show sync statistics (row counts, date ranges).",
    },
}


def route(mode: str = "", **kwargs):
    """Dispatch FCA mode call."""
    from data_sources.cvm.fca.sync_engine import sync
    from data_sources.cvm.fca.query_engine import query
    from data_sources.cvm.fca.status_reporter import status

    dispatch = {
        "sync": sync,
        "query": query,
        "status": status,
    }

    if mode not in dispatch:
        return {"status": "error",
                "error": f"Unknown FCA mode '{mode}'. Available: {list(dispatch.keys())}"}

    return dispatch[mode](**kwargs)
