"""skills/b3/__init__.py -- B3 skills domain root.

Auto-discovered by skills/dispatcher.py. Scans skills/b3/ for
sub-domain packages (index, etc.) with MANIFEST + route().
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

MANIFEST = {
    "domain":          "b3",
    "description":     (
        "B3 (Brasil, Bolsa, Balcao) skills. "
        "index: index composition dashboard (IBOV, SMLL, BDRX, IFIX, IDIV)."
    ),
    "has_sub_domains": True,
}

_SUB_DOMAINS: dict[str, Any] | None = None


def _discover_sub_domains() -> dict[str, Any]:
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
        module_path = f"skills.b3.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "sub_domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            _SUB_DOMAINS[manifest["sub_domain"]] = module
        except Exception as e:
            print(f"[b3] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return _SUB_DOMAINS


def route(sub_domain: str = "", mode: str = "", **kwargs: Any) -> Any:
    """Route skill(domain='b3', sub_domain=..., mode=...) calls."""
    sub_domains = _discover_sub_domains()

    if not sub_domains:
        return {"status": "error", "error": "No b3 sub-domains found in skills/b3/"}

    if not sub_domain:
        if len(sub_domains) == 1:
            sub_domain = next(iter(sub_domains))
        else:
            return {
                "status": "error",
                "error":  f"b3 has multiple sub-domains. Specify sub_domain: {list(sub_domains.keys())}",
            }

    if sub_domain not in sub_domains:
        return {
            "status": "error",
            "error":  f"Unknown b3 sub-domain '{sub_domain}'. Available: {list(sub_domains.keys())}",
        }

    return sub_domains[sub_domain].route(mode=mode, **kwargs)
