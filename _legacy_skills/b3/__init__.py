"""
skills/b3/__init__.py -- B3 domain root manifest and sub-domain router.

Deploy to: D:\mcp\agent\skills\b3\__init__.py

Sub-domains:
  b3_api  -- B3 market data: prices, quotes, instruments
  b3_cvm  -- Identity bridge: ticker <-> CNPJ <-> CD_CVM <-> dfp_itr_ids

DECISION: Auto-discovery of sub-domains via _discover_sub_domains().
Adding a new B3 sub-domain (e.g. b3_fii, b3_options) requires only
creating skills/b3/<new_name>/__init__.py with MANIFEST + route().
Zero changes to this file.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

MANIFEST = {
    "domain":          "b3",
    "description":     (
        "Brazilian B3 stock exchange. "
        "b3_api: market data (prices, quotes). "
        "b3_cvm: identity bridge (ticker->CNPJ->CD_CVM->dfp_itr_ids)."
    ),
    "has_sub_domains": True,
}


def _discover_sub_domains() -> dict[str, Any]:
    """Scan skills/b3/ for sub-domain packages with MANIFEST + route()."""
    sub_domains: dict[str, Any] = {}
    here = Path(__file__).resolve().parent

    for item in sorted(here.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        if not (item / "__init__.py").exists():
            continue
        module_path = f"skills.b3.{item.name}"
        try:
            module   = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            sub_domains[manifest["domain"]] = module
        except Exception as e:
            print(f"[b3/__init__] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return sub_domains


_SUB_DOMAINS: dict[str, Any] = {}


def _get_sub_domains() -> dict[str, Any]:
    global _SUB_DOMAINS
    if not _SUB_DOMAINS:
        _SUB_DOMAINS = _discover_sub_domains()
    return _SUB_DOMAINS


def route(sub_domain: str, mode: str, **kwargs: Any) -> Any:
    subs = _get_sub_domains()

    if sub_domain == "all":
        results = {}
        for name, module in subs.items():
            manifest  = getattr(module, "MANIFEST", {})
            mode_info = manifest.get("modes", {}).get(mode, {})
            if mode_info.get("include_in_all", False):
                try:
                    sig   = inspect.signature(module.route)
                    valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
                    results[name] = module.route(sub_domain=name, mode=mode, **valid)
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
        return {"status": "success", "results": results}

    if not sub_domain:
        if len(subs) == 1:
            sub_domain = next(iter(subs))
        else:
            return {"status": "error",
                    "error": f"sub_domain required. Available: {list(subs)}"}

    module = subs.get(sub_domain)
    if module is None:
        return {"status": "error",
                "error": f"Unknown sub_domain '{sub_domain}'. Available: {list(subs)}"}

    sig   = inspect.signature(module.route)
    valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return module.route(sub_domain=sub_domain, mode=mode, **valid)
