"""skills/bcb/__init__.py -- BCB domain manifest and sub-domain router.

Auto-discovered by skills/dispatcher.py. Scans skills/bcb/ for sub-domain
packages (macro) with MANIFEST + route().

Skills are analytical views that COMBINE multiple BCB data sources with
domain reasoning. They are read-only - no sync. The route() wrapper in each
skill's __init__.py declares required_sources so the sync guard can verify
freshness before dispatch.

Sub-domains:
  macro -- Brazilian macro-economic dashboard (rates, inflation, fx)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

MANIFEST = {
    "domain":          "bcb",
    "description":     (
        "BCB analytical skills. "
        "macro: dashboard of Selic/CDI/TR/IPCA/IGP-M/USD-BRL via SGS data source."
    ),
    "has_sub_domains": True,
}


_SUB_DOMAINS: dict[str, Any] | None = None


def _discover_sub_domains() -> dict[str, Any]:
    """Scan skills/bcb/ for sub-domain packages with MANIFEST + route()."""
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
        module_path = f"skills.bcb.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "sub_domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            _SUB_DOMAINS[manifest["sub_domain"]] = module
        except Exception as e:
            print(f"[skills.bcb] WARNING: failed to load {module_path}: {e}",
                  file=sys.stderr)

    return _SUB_DOMAINS


def route(sub_domain: str = "", mode: str = "", **kwargs: Any) -> Any:
    """Route skill(domain="bcb", sub_domain=..., mode=...) calls.

    Mirrors skills/cvm/__init__.py routing: auto-select if only one
    sub-domain, "all" fans out to include_in_all=True modes, otherwise
    dispatch directly to the named sub-domain.
    """
    sub_domains = _discover_sub_domains()

    if not sub_domains:
        return {"status": "error", "error": "No bcb skills found in skills/bcb/"}

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
        return {"status": "ok", "domain": "bcb",
                "sub_domain": "all", "results": results}

    if not sub_domain:
        if len(sub_domains) == 1:
            sub_domain = next(iter(sub_domains))
        else:
            return {
                "status": "error",
                "error":  f"bcb has multiple skills. Specify sub_domain: "
                          f"{list(sub_domains.keys())}",
            }

    if sub_domain not in sub_domains:
        return {
            "status": "error",
            "error":  f"Unknown bcb skill '{sub_domain}'. Available: "
                      f"{list(sub_domains.keys())}",
        }

    return sub_domains[sub_domain].route(mode=mode, **kwargs)
