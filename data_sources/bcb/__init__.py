"""data_sources/bcb/__init__.py -- BCB domain manifest and sub-domain router.

Auto-discovered by data_sources/dispatcher.py. Scans data_sources/bcb/ for
sub-domain packages (sgs) with MANIFEST + route().

BCB = Banco Central do Brasil (Brazilian Central Bank). Provides public,
free, no-auth macro-economic time series via the SGS API.

Sub-domains:
  sgs -- Sistema Gerenciador de Series Temporais (12 curated macro series)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

MANIFEST = {
    "domain":          "bcb",
    "description":     (
        "BCB (Banco Central do Brasil) data sources. "
        "sgs: 12 curated macro time series (Selic, CDI, TR, IPCA, IGP-M, "
        "USD/BRL, PIB, etc.) via the public SGS API - no auth required."
    ),
    "has_sub_domains": True,
}


_SUB_DOMAINS: dict[str, Any] | None = None


def _discover_sub_domains() -> dict[str, Any]:
    """Scan data_sources/bcb/ for sub-domain packages with MANIFEST + route()."""
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
        module_path = f"data_sources.bcb.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "sub_domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            _SUB_DOMAINS[manifest["sub_domain"]] = module
        except Exception as e:
            print(f"[data_sources.bcb] WARNING: failed to load {module_path}: {e}",
                  file=sys.stderr)

    return _SUB_DOMAINS


def route(sub_domain: str = "", mode: str = "", **kwargs: Any) -> Any:
    """Route data_source(domain="bcb", sub_domain=..., mode=...) calls.

    sub_domain=""    -- auto-select if only one sub-domain, error if multiple
    sub_domain="all" -- run mode on all sub-domains with include_in_all=True
    sub_domain="x"   -- route directly to sub-domain x
    """
    sub_domains = _discover_sub_domains()

    if not sub_domains:
        return {"status": "error",
                "error": "No bcb sub-domains found in data_sources/bcb/"}

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
                "error":  f"bcb has multiple sub-domains. Specify sub_domain: "
                          f"{list(sub_domains.keys())}",
            }

    if sub_domain not in sub_domains:
        return {
            "status": "error",
            "error":  f"Unknown bcb sub-domain '{sub_domain}'. Available: "
                      f"{list(sub_domains.keys())}",
        }

    return sub_domains[sub_domain].route(mode=mode, **kwargs)
