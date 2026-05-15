"""
skills/dispatcher.py -- Single MCP @tool entry point for all skill domains.

ARCHITECTURE
------------
skill(domain, sub_domain, mode, params)

  domain     -- top-level domain: "b3", "cvm", "news", etc.
  sub_domain -- sub-domain within domain: "b3_api", "cvm_api", "cvm_register"
                "" or omitted = auto-select if only one sub-domain exists
                "all" = run mode on ALL sub-domains (only those with include_in_all=True)
  mode       -- operation: "sync", "query", "status", "search", etc.
  params     -- JSON string with mode-specific args: '{"ticker":"PETR4","limit":5}'
                "" = no params, use function defaults

ZERO-MAINTENANCE DESIGN
-----------------------
Adding a new domain:
  1. Create skills/<domain>/__init__.py with MANIFEST + route()
  2. Done. Dispatcher auto-discovers it on next server restart.

Adding a new sub-domain to an existing domain:
  1. Create skills/<domain>/<sub_domain>/__init__.py with MANIFEST + route()
  2. Done. Domain router auto-discovers it.

Adding new params to a sub-domain function:
  1. Add the param to the function signature
  2. Pass it in params JSON: '{"new_param": "value"}'
  3. Done. No changes to dispatcher or any other file.

WHY params AS JSON STRING
--------------------------
FastMCP builds the MCP JSON schema from the @tool function signature.
Explicit typed params require editing dispatcher for every new domain param.
JSON string solves this: 4 stable typed params forever, arbitrary domain args
passed as '{"key": "value"}' -- natural for LLMs which already output JSON.

include_in_all FLAG
-------------------
sub_domain="all" only runs modes where include_in_all=True in the MANIFEST.
Default is False -- opt-in. Batch-safe modes (sync, status) set True.
Param-requiring modes (query, search, lookup) set False.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from registry import tool


def _discover_domains() -> dict:
    """Scan skills/ for domain packages with MANIFEST + route()."""
    domains: dict = {}
    skills_dir = Path(__file__).resolve().parent

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue
        module_path = f"skills.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "domain" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            domains[manifest["domain"]] = module
        except Exception as e:
            print(f"[dispatcher] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return domains


_DOMAINS: dict = _discover_domains()


def _build_docstring() -> str:
    lines = [
        "Execute a skill from any registered domain.",
        "",
        "skill(domain, sub_domain='', mode='', params='')",
        "  params = JSON string: '{\"ticker\":\"PETR4\",\"limit\":5}'",
        "  sub_domain='all' runs mode on all sub-domains where include_in_all=True",
        "",
    ]
    for domain_name, module in _DOMAINS.items():
        manifest = module.MANIFEST
        has_sub  = manifest.get("has_sub_domains", False)
        lines.append(f'domain="{domain_name}" -- {manifest.get("description","")[:70]}')
        if has_sub:
            discover_fn = getattr(module, "_discover_sub_domains", None)
            sub_domains = discover_fn() if discover_fn else {}
            for sd_name, sd_mod in sub_domains.items():
                sd_m = sd_mod.MANIFEST
                lines.append(f'  sub_domain="{sd_name}"')
                for m_name, m_info in sd_m.get("modes", {}).items():
                    tag = " [sync_all]" if m_info.get("include_in_all") else ""
                    lines.append(f'    mode="{m_name}"{tag} -- {m_info.get("description","")[:55]}')
                    exs = m_info.get("examples", [])
                    if exs:
                        lines.append(f'      e.g. {exs[0]}')
        else:
            for m_name, m_info in manifest.get("modes", {}).items():
                lines.append(f'  mode="{m_name}" -- {m_info.get("description","")[:60]}')
                exs = m_info.get("examples", [])
                if exs:
                    lines.append(f'    e.g. {exs[0]}')
        lines.append("")
    return "\n".join(lines)


@tool
def skill(
    domain:     str,
    sub_domain: str = "",
    mode:       str = "",
    params:     str = "",
) -> dict:
    """Docstring set dynamically below."""
    # Parse params JSON
    kwargs: dict = {}
    if params:
        try:
            kwargs = json.loads(params)
            if not isinstance(kwargs, dict):
                return {"status": "error", "error": f"params must be a JSON object, got: {type(kwargs).__name__}"}
        except json.JSONDecodeError as e:
            return {"status": "error",
                    "error": f"params is not valid JSON: {e}. Example: '{{\"ticker\":\"PETR4\"}}'"}

    domain = domain.strip().lower()
    if domain not in _DOMAINS:
        return {
            "status": "error",
            "error":  f"Unknown domain '{domain}'. Available: {list(_DOMAINS.keys())}",
        }

    module = _DOMAINS[domain]
    return module.route(sub_domain=sub_domain.strip(), mode=mode.strip(), **kwargs)


skill.__doc__ = _build_docstring()
