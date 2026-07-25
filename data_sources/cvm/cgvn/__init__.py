"""data_sources/cvm/cgvn/__init__.py -- CGVN (Código de Governança) data source manifest.

CGVN = Código de Governança e Melhores Práticas. Companies report which
recommended governance practices they adopt (Sim/Não/Parcialmente).

Two tables:
  cgvn_documents  -- filing metadata (who filed, when, link to PDF)
  cgvn_practices  -- governance practices (recommended vs adopted, chapter, principle)

URL pattern:
  http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/cgvn_cia_aberta_YYYY.zip

Each ZIP contains:
  cgvn_cia_aberta.csv           -- document index
  cgvn_cia_aberta_praticas.csv  -- practices (the valuable one)
"""

from __future__ import annotations

MANIFEST = {
    "sub_domain": "cgvn",
    "description": (
        "CGVN — Código de Governança e Melhores Práticas. "
        "sync: download annual ZIPs from CVM. "
        "query: governance practices by company. "
        "status: sync statistics."
    ),
    "source": "CVM CGVN API (http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/)",
    "storage": "SQLite — cgvn.db",
    "has_sub_domains": False,
    "modes": {
        "sync":   "Download + parse CGVN ZIPs from CVM into cgvn.db.",
        "query":  "Query governance practices by company (CNPJ/ticker/name).",
        "status": "Show sync statistics (row counts, date ranges).",
    },
}


def route(mode: str = "", **kwargs):
    """Dispatch CGVN mode call."""
    from data_sources.cvm.cgvn.sync_engine import sync
    from data_sources.cvm.cgvn.query_engine import query
    from data_sources.cvm.cgvn.status_reporter import status

    dispatch = {
        "sync": sync,
        "query": query,
        "status": status,
    }

    if mode not in dispatch:
        return {"status": "error",
                "error": f"Unknown CGVN mode '{mode}'. Available: {list(dispatch.keys())}"}

    return dispatch[mode](**kwargs)
