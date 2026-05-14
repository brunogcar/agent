"""
skills/cvm/__init__.py -- CVM financial statements domain manifest.

Routes skill(domain="cvm", mode=...) calls to cvm_api.py functions.

MODES
-----
  completo_anual  -- all account codes, annual  (DFP, meses=12)
  completo_trim   -- all account codes, quarterly (ITR, meses=3/6/9)
  resumo_anual    -- key metrics, annual
  resumo_trim     -- key metrics, quarterly
  search          -- find companies by name or CNPJ
  status          -- rapina.db file info and row counts

FUTURE MODES (planned)
  dividends       -- dividend history from fre table (when populated)
  shareholders    -- shareholder structure from fre table
  link_b3         -- cross-reference with b3_api via ISIN/CNPJ

DATA SOURCE
-----------
rapina.db built by rapinav2 (https://github.com/dude333/rapinav2).
Update with: rapinav2 atualizar --all
Stored at: memory_db/cvm/rapina.db (read-only from this skill).
"""

from __future__ import annotations

from skills.cvm.cvm_api import (
    completo_anual,
    completo_trim,
    resumo_anual,
    resumo_trim,
    search_companies,
    db_status,
)


MANIFEST: dict = {
    "domain":      "cvm",
    "description": (
        "CVM (Brazilian SEC) financial statements from rapina.db. "
        "Annual and quarterly balance sheet, income statement, and cash flow "
        "for all ~700 listed Brazilian companies from 2009 to present."
    ),
    "source":      "rapina.db (rapinav2 by dude333) -- updated via: rapinav2 atualizar --all",
    "storage":     "memory_db/cvm/rapina.db (read-only, 1.5 GB SQLite)",

    "modes": {

        "completo_anual": {
            "fn":          completo_anual,
            "description": "All account codes, annual data (DFP, meses=12), consolidated. "
                           "Equivalent to rapinav2 'completo anual (consolid)' sheet.",
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Specific years e.g. [2023,2024]. Default: last 5.",
                "consolidado": "int. 1=consolidated (default), 0=individual statements.",
                "limit_years": "int. Max years when anos not set. Default: 5.",
            },
            "examples": [
                'skill(domain="cvm", mode="completo_anual", company="PETROBRAS")',
                'skill(domain="cvm", mode="completo_anual", company="33.000.167/0001-01", anos=[2023,2024])',
                'skill(domain="cvm", mode="completo_anual", company="VALE", limit_years=3)',
            ],
        },

        "completo_trim": {
            "fn":          completo_trim,
            "description": "All account codes, quarterly data (ITR, meses=3/6/9), consolidated. "
                           "Equivalent to 'completo trim. (consolid)'. "
                           "NOTE: periods are cumulative (meses=6 is Jan-Jun total, not Q2 alone).",
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Specific years. Default: last 3.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
                "limit_years": "int. Max years. Default: 3.",
            },
            "examples": [
                'skill(domain="cvm", mode="completo_trim", company="PETROBRAS")',
                'skill(domain="cvm", mode="completo_trim", company="ITAU", anos=[2024,2025])',
            ],
        },

        "resumo_anual": {
            "fn":          resumo_anual,
            "description": "Key financial metrics only, annual data. "
                           "Equivalent to 'resumo anual (consolid)'. "
                           "20 metrics: revenue, EBIT, net income, assets, equity, cash flows.",
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Specific years. Default: last 10.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
                "limit_years": "int. Max years. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", mode="resumo_anual", company="PETROBRAS")',
                'skill(domain="cvm", mode="resumo_anual", company="VALE", limit_years=5)',
                'skill(domain="cvm", mode="resumo_anual", company="ITAU UNIBANCO", anos=[2022,2023,2024])',
            ],
        },

        "resumo_trim": {
            "fn":          resumo_trim,
            "description": "Key financial metrics only, quarterly data. "
                           "Equivalent to 'resumo trim. (consolid)'. "
                           "Same 20 metrics as resumo_anual but for quarterly periods.",
            "params": {
                "company":     "str. Company name, partial name, or CNPJ. Required.",
                "anos":        "list[int]. Specific years. Default: last 4.",
                "consolidado": "int. 1=consolidated (default), 0=individual.",
                "limit_years": "int. Max years. Default: 4.",
            },
            "examples": [
                'skill(domain="cvm", mode="resumo_trim", company="PETROBRAS")',
                'skill(domain="cvm", mode="resumo_trim", company="WEGE", anos=[2024,2025])',
            ],
        },

        "search": {
            "fn":          search_companies,
            "description": "Find companies by name fragment or CNPJ. "
                           "Use this first if unsure of the exact company name.",
            "params": {
                "query": "str. Company name fragment or partial CNPJ. Required.",
                "limit": "int. Max results. Default: 10.",
            },
            "examples": [
                'skill(domain="cvm", mode="search", query="PETRO")',
                'skill(domain="cvm", mode="search", query="ITAU")',
                'skill(domain="cvm", mode="search", query="33.000.167")',
            ],
        },

        "status": {
            "fn":          db_status,
            "description": "Show rapina.db file info: size, row counts, date range.",
            "params": {},
            "examples": [
                'skill(domain="cvm", mode="status")',
            ],
        },
    },
}


def route(mode: str, **kwargs) -> dict:
    """
    Route skill(domain='cvm', mode=...) to the correct cvm_api function.

    ARCHITECTURE DECISION: route() filters kwargs to only what the target
    function accepts. This means the dispatcher can pass ALL params from its
    unified signature without each domain needing to know about other domains'
    params. New params added to the dispatcher signature never break existing
    domains.

    How it works:
      1. Get the target function from the manifest
      2. Inspect its signature to find accepted param names
      3. Filter kwargs to only the accepted ones
      4. Call fn(**filtered_kwargs)

    This is the correct pattern for a multi-domain dispatcher where the
    dispatcher signature is the union of all domain param sets.
    """
    if mode not in MANIFEST["modes"]:
        return {
            "status": "error",
            "error":  f"Unknown mode '{mode}' for domain 'cvm'. "
                      f"Available: {list(MANIFEST['modes'].keys())}",
        }

    import inspect
    fn   = MANIFEST["modes"][mode]["fn"]
    sig  = inspect.signature(fn)

    # Filter to only params the function actually accepts
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {
            "status": "error",
            "domain": "cvm",
            "mode":   mode,
            "error":  str(e),
        }
