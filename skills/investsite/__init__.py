"""skills/investsite/__init__.py -- Investsite skill manifest + router.

Fetches financial data from investsite.com.br (per-ticker pages).

Unlike CVM/B3 skills which read from local databases, this skill fetches
live data from the web. No sync, no local DB — each call hits the site.

6 modes:
  indicators (default) — main page: 10 tables (prices, DRE, returns, balance, cashflow)
  statements          — full financial statement (BPA/BPP/DRE/DFC/DVA) with % total
  events              — periodic info by category with CVM PDF links
  summary             — combined: key indicators + latest events
  listing             — list available event categories
  dashboard           — multi-tab composition (Overview/Key Indicators/Latest Events)

[v1.1] Modular split: investsite.py monolith replaced by auto-discovery of
modes/*.py files via importlib (same pattern as governance/screener/
shareholders/insider/historical). fetcher.py + parsers.py are KEPT as
separate modules — only investsite.py was split. The MANIFEST keeps
"domain" (not "sub_domain") because investsite is a TOP-LEVEL flat domain,
not under cvm/. route() signature stays route(sub_domain="", mode="",
**kwargs) — the sub_domain param is accepted for dispatcher compatibility
but ignored.

Auto-discovery:
  1. Import _registry to ensure the MODES dict exists.
  2. Auto-discover all modes/*.py files via importlib.
  3. Each mode module's @register_mode decorator populates MODES.
  4. build_manifest_modes() turns the registry into MANIFEST["modes"].

Adding a new mode = drop a file in modes/ + register_mode(). No edits to
__init__.py or _registry.py needed.
"""

from __future__ import annotations
import importlib
import inspect
from pathlib import Path

# Import _registry to ensure MODES dict exists.
from skills.investsite._registry import MODES, build_manifest_modes  # noqa: F401

# Auto-discover all mode modules from modes/ subdirectory.
# Each module's @register_mode decorator populates MODES.
_modes_dir = Path(__file__).parent / "modes"
for _py_file in sorted(_modes_dir.glob("*.py")):
    if _py_file.name == "__init__.py":
        continue
    _module_name = f"skills.investsite.modes.{_py_file.stem}"
    importlib.import_module(_module_name)


# Build MANIFEST from the registered modes.
MANIFEST = {
    "domain":       "investsite",
    "description":  (
        "Financial data from investsite.com.br (live web scraping). "
        "Per-ticker indicators, full statements, periodic events with CVM links. "
        "No local DB — fetches live each call. "
        "dashboard: multi-tab composition (Overview/Key Indicators/Latest Events)."
    ),
    "has_sub_domains": False,
    "source":  "investsite.com.br (live HTTP)",
    "storage": "in-memory cache only (1h TTL)",
    "modes": build_manifest_modes(),
}


def route(sub_domain: str = "", mode: str = "", **kwargs) -> dict:
    """Dispatch investsite mode call.

    Args:
        sub_domain: Ignored (investsite is a flat domain — kept for
            dispatcher compatibility with CVM-style routes).
        mode: Mode name ("indicators", "statements", "events",
            "summary", "listing", "dashboard"). Required — empty returns
            an error.
        **kwargs: Forwarded to the mode function (filtered by the function's
            signature — unknown kwargs are silently dropped).

    Returns:
        Mode-specific dict on success, or ``{"status": "error", "error": ...}``
        on bad mode name or runtime failure.
    """
    # sub_domain is intentionally ignored — investsite is a flat domain.
    _ = sub_domain

    if not mode:
        return {"status": "error",
                "error": f"mode required. Options: {list(MODES.keys())}"}
    if mode not in MODES:
        return {"status": "error",
                "error": f"Unknown mode '{mode}'. Available: {list(MODES.keys())}"}

    spec = MODES[mode]
    fn = spec.fn
    sig = inspect.signature(fn)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}

    try:
        return fn(**filtered)
    except Exception as e:
        return {"status": "error", "domain": "investsite",
                "mode": mode, "error": str(e)}
