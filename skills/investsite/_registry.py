"""skills/investsite/_registry.py — Mode registry for investsite skill.

Delegates to skills._base for the shared ModeSpec + register_mode +
build_manifest_modes infrastructure. This file exists to give investsite
its own isolated MODES dict + to provide a stable import path for mode files:
    from skills.investsite._registry import register_mode

Note: investsite is a flat top-level domain (not under cvm/), so the
MANIFEST in __init__.py uses "domain" instead of "sub_domain" and includes
"has_sub_domains": False. The route() factory is called with
accept_sub_domain=True so the dispatcher exposes a route(sub_domain="",
mode="", **kwargs) signature for compatibility with the CVM-style
dispatcher (sub_domain is accepted but ignored).
"""
from __future__ import annotations

from skills._base import make_registry, build_manifest_modes, list_modes, get_mode

# Create investsite's own isolated MODES dict + register_mode decorator.
MODES, register_mode = make_registry()
