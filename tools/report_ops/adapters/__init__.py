"""report_ops/adapters/ — Skill JSON → report-ready table data adapters.

WHY THIS LAYER EXISTS
---------------------
Skills return nested, domain-rich JSON (metrics + ratios + periods + sources).
The report tool is intentionally domain-agnostic: it only knows how to render
tables/KPIs/sources. The adapters sit between them, flattening each skill's
output into the generic table data shape:

    {"sections": [...], "kpis": [...], "sources": [...]}

This keeps the report tool free of CVM/B3 knowledge and keeps skill output
formats stable (skills don't need to know reports exist).

REGISTRATION
------------
Each adapter module registers its adapters via ``@register_adapter(name)``.
``__init__.py`` imports the modules so their decorators run at first use.
Adapters are pure functions: ``adapter(skill_result: dict) -> table_data: dict``.

USAGE FROM THE LLM
------------------
The LLM pipes a skill result straight into the table action:

    skill(domain="cvm", sub_domain="financials", mode="quarterly",
          params='{"company":"PETR4"}')          -> <financials JSON>

    report(action="table", title="PETR4 Financials",
           data=<financials JSON>,
           config={"adapter": "financials_quarterly"})

The same adapter is honoured by ``report(action="export", config={"format":"xlsx",
"adapter":"..."})`` so a skill result can be exported to Excel in one call.

ADAPTER NAMING
--------------
``<skill>_<mode>`` — e.g. ``financials_quarterly``, ``valuation_ratios``,
``shareholders_free_float``, ``dividends_annual``. See ``list_adapters()``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

# name -> callable(skill_result: dict) -> table_data: dict
ADAPTERS: Dict[str, Callable[[dict], dict]] = {}


def register_adapter(name: str) -> Callable:
    """Register a skill-result → table-data adapter under ``name``."""
    def decorator(func: Callable[[dict], dict]) -> Callable[[dict], dict]:
        if name in ADAPTERS:
            raise ValueError(f"Duplicate adapter registration: '{name}'")
        ADAPTERS[name] = func
        return func
    return decorator


def apply_adapter(name: str, data: Any) -> dict:
    """Run the named adapter over ``data``. Raises ValueError if unknown."""
    name = (name or "").strip()
    func = ADAPTERS.get(name)
    if func is None:
        raise ValueError(
            f"Unknown adapter '{name}'. Available: {sorted(ADAPTERS.keys())}"
        )
    if not isinstance(data, dict):
        raise ValueError(
            f"Adapter '{name}' requires a dict (skill result), got {type(data).__name__}"
        )
    return func(data)


def list_adapters() -> List[str]:
    """Return sorted adapter names (for ``report(action='help')`` / docs)."""
    return sorted(ADAPTERS.keys())


# ── Shared helpers ───────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """True if a skill result is successful enough to table-ify."""
    return isinstance(result, dict) and result.get("status") == "ok"


def _error_table(result: dict, *, title: str = "Data unavailable") -> dict:
    """Build a single-section table reporting a skill error/no-data state.

    Keeps the table action usable even when a skill returns not_found/not_synced
    — the LLM sees the cause inline instead of a render crash.
    """
    if isinstance(result, dict):
        status = result.get("status", "error")
        err = result.get("error") or result.get("message") or "No data returned"
    else:
        status, err = "error", "Unexpected payload type"
    return {
        "sections": [{
            "title": title,
            "columns": ["Status", "Detail"],
            "rows": [[status, str(err)]],
            "formats": {"Detail": "text"},
            "note": "The underlying skill did not return usable data.",
        }],
        "kpis": [],
        "sources": [],
    }


def _kv_section(title: str, rows: list[tuple[str, Any, str]]) -> dict:
    """Build a key-value (indicator) section.

    rows: list of (label, raw_value, spec). Values are pre-formatted to strings
    via apply_fmt so the column uses the "text" spec. This is ideal for ratio
    tables where each row has its own unit (P/L is a multiple, Market Cap is BRL).
    """
    from tools.report_ops.formats import apply_fmt
    return {
        "title": title,
        "columns": ["Indicador", "Valor"],
        "rows": [[label, apply_fmt(value, spec)] for label, value, spec in rows],
        "formats": {"Valor": "text"},
    }


def _safe_num(v: Any) -> Any:
    """Pass through numbers; coerce numeric strings; leave None/blank as None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


# Importing the modules here triggers their @register_adapter decorators.
# Lazy import keeps MCP startup fast (only runs when an adapter is first used).
from tools.report_ops.adapters import financials  # noqa: E402,F401
from tools.report_ops.adapters import financials_chart  # noqa: E402,F401
from tools.report_ops.adapters import valuation   # noqa: E402,F401
from tools.report_ops.adapters import shareholders  # noqa: E402,F401
from tools.report_ops.adapters import dividends   # noqa: E402,F401
from tools.report_ops.adapters import comparison  # noqa: E402,F401
from tools.report_ops.adapters import cotahist_chart  # noqa: E402,F401
from tools.report_ops.adapters import cotahist_candlestick  # noqa: E402,F401
from tools.report_ops.adapters import screener  # noqa: E402,F401
