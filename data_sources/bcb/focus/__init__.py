"""data_sources/bcb/focus/__init__.py -- Focus sub-domain manifest and router.

BCB Focus = Boletim Focus (weekly market expectations survey). Public, free,
no auth. Olinda OData API exposes per-indicator market expectations:
median, mean, min, max + respondent count.

4 curated indicators x frequency:
  - IPCA   (monthly)   -- inflation expectation for a specific month
  - Selic  (annual)    -- Selic target rate for a specific year
  - PIB    (annual)    -- GDP real growth for a specific year
  - Cambio (monthly)   -- USD/BRL exchange rate for a specific month

7 modes: sync_all, sync_expectations, sync_indicator, expectations, last,
summary, status.

Data source: olinda.bcb.gov.br (live OData REST API, no auth)
Storage:     memory_db/bcb/focus.db

The route() dispatcher follows the sgs pattern: lazy-imports each mode's
module on first dispatch, filters kwargs by the target function's signature,
and returns a structured dict (status / error / traceback on failure).

Auto-discovered by data_sources/bcb/__init__.py (any sub-directory with
__init__.py + MANIFEST + route() is picked up automatically).
"""

from __future__ import annotations
import inspect

MANIFEST = {
    "sub_domain":  "focus",
    "description": (
        "BCB Focus (Boletim Focus) - market expectations survey via the "
        "Olinda OData API. 4 indicators (IPCA, Selic, PIB, Cambio) x "
        "frequency (monthly/annual). Public API, no auth. Thread-safe "
        "concurrent fetcher (Semaphore(5))."
    ),
    "source":  "olinda.bcb.gov.br (live OData REST API, no auth)",
    "storage": "memory_db/bcb/focus.db",
    "modes": {
        "sync_all": {
            "description": (
                "Sync every (indicador, frequency) in DEFAULT_INDICATORS "
                "concurrently (Semaphore(5), ~4 HTTP calls). Idempotent via "
                "INSERT OR REPLACE."
            ),
            "include_in_all": True,
            "params": {
                "force": "bool. Re-fetch even if recently synced. Default: false.",
                "top":   "int. Max records per fetch. Default: 100.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="sync_all")',
            ],
        },
        "sync_expectations": {
            "description": "Sync one (indicador, frequency) pair (most-recent top N).",
            "include_in_all": True,
            "params": {
                "indicador": "str. 'IPCA', 'Selic', 'PIB', 'Cambio'. Required.",
                "frequency": "str. 'monthly' or 'annual'. Required.",
                "top":       "int. Max records. Default: 100.",
                "force":     "bool. Default: false.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="sync_expectations", '
                'params=\'{"indicador":"IPCA","frequency":"monthly"}\')',
            ],
        },
        "sync_indicator": {
            "description": "Sync one indicator using its primary frequency from DEFAULT_INDICATORS.",
            "include_in_all": False,
            "params": {
                "indicador": "str. Required.",
                "force":     "bool. Default: false.",
                "top":       "int. Default: 100.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="sync_indicator", '
                'params=\'{"indicador":"Selic"}\')',
            ],
        },
        "expectations": {
            "description": "Query the most recent N expectations for an indicator.",
            "include_in_all": True,
            "params": {
                "indicador": "str. Required.",
                "frequency": "str. 'monthly' or 'annual'. Required.",
                "limit":     "int. Max results. Default: 50.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="expectations", '
                'params=\'{"indicador":"IPCA","frequency":"monthly","limit":20}\')',
            ],
        },
        "last": {
            "description": "Get the most recent expectation for an indicator.",
            "include_in_all": True,
            "params": {
                "indicador": "str. Required.",
                "frequency": "str. Required.",
            },
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="last", '
                'params=\'{"indicador":"Selic","frequency":"annual"}\')',
            ],
        },
        "summary": {
            "description": "Catalog overview: every (indicador, frequency) pair + row counts.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="summary")',
            ],
        },
        "status": {
            "description": "Show focus.db stats: per-indicator row counts + last sync timestamps.",
            "include_in_all": True,
            "params": {},
            "examples": [
                'data_source(domain="bcb", sub_domain="focus", mode="status")',
            ],
        },
    },
}


def route(mode: str = "", **kwargs) -> dict:
    """Dispatch focus mode call (sgs pattern: lazy-import + filter kwargs)."""
    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MANIFEST['modes'].keys())}"}
    if mode not in MANIFEST["modes"]:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MANIFEST['modes'].keys())}"}

    try:
        if mode == "sync_all":
            from data_sources.bcb.focus.sync_engine import sync_all as _fn
        elif mode == "sync_expectations":
            from data_sources.bcb.focus.sync_engine import sync_expectations as _fn
        elif mode == "sync_indicator":
            from data_sources.bcb.focus.sync_engine import sync_indicator as _fn
        elif mode == "expectations":
            from data_sources.bcb.focus.query_engine import expectations as _fn
        elif mode == "last":
            from data_sources.bcb.focus.query_engine import last_value as _fn
        elif mode == "summary":
            from data_sources.bcb.focus.query_engine import summary as _fn
        elif mode == "status":
            from data_sources.bcb.focus.status_reporter import status as _fn
        else:
            return {"status": "error", "error": f"Mode '{mode}' not implemented."}

        sig = inspect.signature(_fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return _fn(**filtered)

    except FileNotFoundError as e:
        return {"status": "not_synced", "error": str(e)}
    except Exception as e:
        import traceback
        return {
            "status":     "error",
            "sub_domain": "focus",
            "mode":       mode,
            "error":      str(e),
            "traceback":  traceback.format_exc(),
        }
