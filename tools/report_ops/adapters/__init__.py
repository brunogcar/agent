"""report_ops/adapters/ — Skill JSON → report-ready table data adapters.

WHY THIS LAYER EXISTS
---------------------
Skills return nested, domain-rich JSON. The report tool is domain-agnostic.
The adapters sit between them, flattening each skill's output into the generic
table data shape: {"sections": [...], "kpis": [...], "sources": [...]}.

REGISTRATION
------------
Each adapter module registers via @register_adapter(name). __init__.py imports
the modules so their decorators run at first use.

USAGE FROM THE LLM
------------------
    report(action="table", data=<skill JSON>, config={"adapter":"financials_quarterly"})

ADAPTER NAMING
--------------
<skill>_<mode> — e.g. financials_quarterly, valuation_ratios, insider_history.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

ADAPTERS: Dict[str, Callable[[dict], dict]] = {}


def register_adapter(name: str) -> Callable:
    def decorator(func: Callable[[dict], dict]) -> Callable[[dict], dict]:
        if name in ADAPTERS:
            raise ValueError(f"Duplicate adapter registration: '{name}'")
        ADAPTERS[name] = func
        return func
    return decorator


def apply_adapter(name: str, data: Any) -> dict:
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
    return sorted(ADAPTERS.keys())


# ── Shared helpers ───────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    return isinstance(result, dict) and result.get("status") == "ok"


def _error_table(result: dict, *, title: str = "Data unavailable") -> dict:
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
    from tools.report_ops.formats import apply_fmt
    return {
        "title": title,
        "columns": ["Indicador", "Valor"],
        "rows": [[label, apply_fmt(value, spec)] for label, value, spec in rows],
        "formats": {"Valor": "text"},
    }


def _safe_num(v: Any) -> Any:
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
# NOTE: financials_chart.py was merged into financials.py (preserved via the
#       original financials.py path; financials_chart.py was deleted).
# NOTE: cotahist_chart.py was renamed to cotahist.py (preserving git history)
#       and cotahist_candlestick.py was merged into cotahist.py (then deleted).
from tools.report_ops.adapters import financials  # noqa: E402,F401
from tools.report_ops.adapters import financials_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import valuation   # noqa: E402,F401
from tools.report_ops.adapters import valuation_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import shareholders  # noqa: E402,F401
from tools.report_ops.adapters import dividends   # noqa: E402,F401
from tools.report_ops.adapters import dividends_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import comparison  # noqa: E402,F401
from tools.report_ops.adapters import comparison_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import cotahist    # noqa: E402,F401
from tools.report_ops.adapters import screener  # noqa: E402,F401
from tools.report_ops.adapters import insider  # noqa: E402,F401
from tools.report_ops.adapters import governance  # noqa: E402,F401
from tools.report_ops.adapters import governance_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import historical  # noqa: E402,F401
from tools.report_ops.adapters import historical_dashboard  # noqa: E402,F401
from tools.report_ops.adapters import backtest  # noqa: E402,F401
from tools.report_ops.adapters import backtest_dashboard  # noqa: E402,F401
