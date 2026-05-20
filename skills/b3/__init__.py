"""
skills/b3/__init__.py -- B3 domain root manifest and router.

=== SUB-DOMAINS ===

  b3_api   -- B3 market data: prices, quotes, instruments, trading info.
              Primary source: B3's public APIs (cotacoes, instrumentos, etc.)
              Modes: query, status, sync (if applicable)

  b3_cvm   -- Company identity bridge: ticker <-> ISIN <-> CNPJ <-> CD_CVM <-> rapina_ids.
              Builds and queries bridge.db (memory_db/cvm/bridge.db).
              Required before calling cvm_* skills with a ticker.
              Modes: sync, status, lookup, resolve, tickers

=== WHY TWO SUB-DOMAINS UNDER b3/ ===
b3_api is pure market data (prices, volumes) -- it speaks to B3's trading APIs.
b3_cvm is identity infrastructure -- it uses B3's ISIN registry to map tickers
to CVM/rapina identifiers. They share the b3/ domain because both depend on
B3 as the authoritative source for Brazilian equity market data.

b3_cvm deliberately does NOT fetch prices or market data.
b3_api deliberately does NOT resolve CNPJ or CVM codes.
Clean separation of concerns.

=== DISPATCHER INTEGRATION ===
skills/dispatcher.py calls:
  1. MANIFEST["has_sub_domains"] = True -> calls _discover_sub_domains()
  2. route(sub_domain, mode, **kwargs)  -> dispatches to correct sub-domain

Auto-discovery: any directory under skills/b3/ with an __init__.py that
defines MANIFEST and route() is automatically registered as a sub-domain.
Adding a new B3 sub-domain requires zero changes to this file.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any


# ── MANIFEST ──────────────────────────────────────────────────────────────────

MANIFEST = {
    "domain":          "b3",
    "description":     (
        "Brazilian B3 stock exchange skills. "
        "b3_api: market data (prices, quotes, instruments). "
        "b3_cvm: company identity bridge (ticker->CNPJ->CD_CVM->rapina_ids)."
    ),
    "has_sub_domains": True,
}


# ── Sub-domain discovery ───────────────────────────────────────────────────────

def _discover_sub_domains() -> dict[str, Any]:
    """
    Scan skills/b3/ for sub-domain packages.

    A valid sub-domain directory must:
      - Be a directory (not a file)
      - Not start with _ or .
      - Contain __init__.py
      - That __init__.py must define MANIFEST["domain"] and route()

    Returns {sub_domain_name: module} dict.

    DECISION: Auto-discovery means zero changes needed here when adding
    new B3 sub-domains (e.g. b3_fii, b3_options in the future).
    Same pattern used by skills/dispatcher.py for top-level domains.
    """
    sub_domains: dict[str, Any] = {}
    here = Path(__file__).resolve().parent

    for item in sorted(here.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        module_path = f"skills.b3.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            sub_domains[manifest["domain"]] = module
        except Exception as e:
            import sys
            print(
                f"[b3/__init__] WARNING: failed to load {module_path}: {e}",
                file=sys.stderr,
            )

    return sub_domains


_SUB_DOMAINS: dict[str, Any] = {}   # populated lazily on first route() call


def _get_sub_domains() -> dict[str, Any]:
    global _SUB_DOMAINS
    if not _SUB_DOMAINS:
        _SUB_DOMAINS = _discover_sub_domains()
    return _SUB_DOMAINS


# ── route() ───────────────────────────────────────────────────────────────────

def route(sub_domain: str, mode: str, **kwargs: Any) -> Any:
    """
    Dispatch a b3 domain call to the correct sub-domain.

    sub_domain: "b3_api" | "b3_cvm"
    mode:       sub-domain specific mode string
    kwargs:     mode-specific parameters

    If sub_domain is empty and only one sub-domain exists, uses it.
    If sub_domain is "all", runs mode on all sub-domains with include_in_all=True.
    """
    subs = _get_sub_domains()

    # Handle sub_domain="all"
    if sub_domain == "all":
        results = {}
        for name, module in subs.items():
            manifest = getattr(module, "MANIFEST", {})
            modes = manifest.get("modes", {})
            mode_info = modes.get(mode, {})
            if mode_info.get("include_in_all", False):
                try:
                    sig   = inspect.signature(module.route)
                    valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
                    results[name] = module.route(sub_domain=name, mode=mode, **valid)
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
        return {"status": "success", "results": results}

    # Handle empty sub_domain: auto-select if unambiguous
    if not sub_domain:
        if len(subs) == 1:
            sub_domain = next(iter(subs))
        else:
            return {
                "status": "error",
                "error": (
                    f"sub_domain required for b3 domain. "
                    f"Available: {list(subs.keys())}"
                ),
            }

    module = subs.get(sub_domain)
    if module is None:
        return {
            "status": "error",
            "error": (
                f"Unknown sub_domain '{sub_domain}' in b3 domain. "
                f"Available: {list(subs.keys())}"
            ),
        }

    # Filter kwargs to what route() actually accepts
    sig   = inspect.signature(module.route)
    valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return module.route(sub_domain=sub_domain, mode=mode, **valid)
