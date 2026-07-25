"""data_sources/cvm/vlmo/__init__.py -- VLMO (Valores Mobiliários) data source manifest.

VLMO = insider trading disclosures. When directors, officers, or controlling
shareholders buy/sell company securities, they must report to CVM.

Two tables:
  vlmo_documents  -- filing metadata (who filed, when, link to PDF)
  vlmo_movements  -- the actual transactions (insider, role, asset, qty, price, date)

URL pattern:
  http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_YYYY.zip

Each ZIP contains:
  vlmo_cia_aberta.csv      -- document index
  vlmo_cia_aberta_con.csv  -- consolidated movements (the valuable one)
"""

from __future__ import annotations

MANIFEST = {
    "sub_domain": "vlmo",
    "description": (
        "VLMO — Valores Mobiliários (insider trading disclosures). "
        "sync: download annual ZIPs from CVM. "
        "query: insider buy/sell transactions by company. "
        "status: sync statistics."
    ),
    "source": "CVM VLMO API (http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/)",
    "storage": "SQLite — vlmo.db",
    "has_sub_domains": False,
    "modes": {
        "sync":   "Download + parse VLMO ZIPs from CVM into vlmo.db.",
        "query":  "Query insider trading movements by company (CNPJ/ticker/name).",
        "status": "Show sync statistics (row counts, date ranges).",
    },
}


def route(mode: str = "", **kwargs):
    """Dispatch VLMO mode call."""
    from data_sources.cvm.vlmo.sync_engine import sync
    from data_sources.cvm.vlmo.query_engine import query
    from data_sources.cvm.vlmo.status_reporter import status

    dispatch = {
        "sync": sync,
        "query": query,
        "status": status,
    }

    if mode not in dispatch:
        return {"status": "error",
                "error": f"Unknown VLMO mode '{mode}'. Available: {list(dispatch.keys())}"}

    return dispatch[mode](**kwargs)
