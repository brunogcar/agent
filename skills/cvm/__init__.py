"""skills/cvm/__init__.py -- CVM domain manifest and sub-domain router.

Auto-discovered by skills/dispatcher.py. Scans skills/cvm/ for sub-domain
packages (shareholders, dividends, etc.) with MANIFEST + route().

Skills are analytical views that COMBINE multiple CVM data sources (dfp, itr,
fre, ipe, cad, bridge) with domain reasoning. They are read-only — no sync.

Sub-domains:
  shareholders -- named shareholders (FRE) + equity structure (DFP BPP)
  dividends    -- individual events (B3) + annual totals (DFP DVA) + filings (IPE)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

MANIFEST = {
    "domain":          "cvm",
    "description":     (
        "CVM analytical skills. "
        "shareholders: ownership + equity structure. "
        "dividends: events + annual totals + filings."
    ),
    "has_sub_domains": True,
}


_SUB_DOMAINS: dict[str, Any] | None = None


def _discover_sub_domains() -> dict[str, Any]:
    """Scan skills/cvm/ for sub-domain packages with MANIFEST + route()."""
    global _SUB_DOMAINS
    if _SUB_DOMAINS is not None:
        return _SUB_DOMAINS

    _SUB_DOMAINS = {}
    here = Path(__file__).resolve().parent

    for item in sorted(here.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue
        module_path = f"skills.cvm.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "sub_domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            _SUB_DOMAINS[manifest["sub_domain"]] = module
        except Exception as e:
            print(f"[skills.cvm] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return _SUB_DOMAINS


def route(sub_domain: str = "", mode: str = "", **kwargs: Any) -> Any:
    """Route skill(domain="cvm", sub_domain=..., mode=...) calls.

    sub_domain=""    -- auto-select if only one sub-domain, error if multiple
    sub_domain="all" -- run mode on all sub-domains with include_in_all=True
    sub_domain="x"   -- route directly to sub-domain x
    """
    sub_domains = _discover_sub_domains()

    if not sub_domains:
        return {"status": "error", "error": "No cvm skills found in skills/cvm/"}

    if sub_domain.lower() == "all":
        results = {}
        for sd_name, sd_module in sub_domains.items():
            manifest = sd_module.MANIFEST
            mode_info = manifest.get("modes", {}).get(mode, {})
            if not mode_info.get("include_in_all", False):
                results[sd_name] = {"status": "skipped",
                                    "reason": f"include_in_all=False for mode '{mode}'"}
                continue
            try:
                results[sd_name] = sd_module.route(mode=mode, **kwargs)
            except Exception as e:
                results[sd_name] = {"status": "error", "error": str(e)}
        return {"status": "ok", "domain": "cvm", "sub_domain": "all", "results": results}

    if not sub_domain:
        if len(sub_domains) == 1:
            sub_domain = next(iter(sub_domains))
        else:
            return {
                "status": "error",
                "error":  f"cvm has multiple skills. Specify sub_domain: {list(sub_domains.keys())}",
            }

    if sub_domain not in sub_domains:
        return {
            "status": "error",
            "error":  f"Unknown cvm skill '{sub_domain}'. Available: {list(sub_domains.keys())}",
        }

    return sub_domains[sub_domain].route(mode=mode, **kwargs)
