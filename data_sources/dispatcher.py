"""data_sources/dispatcher.py — Single MCP @tool entry point for all data sources.

ARCHITECTURE
------------
data_source(domain, sub_domain, mode, params)

  domain     -- top-level domain: "cvm", "b3", etc.
  sub_domain -- sub-domain within domain: "dfp", "itr", etc.
                "" or omitted = auto-select if only one sub-domain exists
                "all" = run mode on ALL sub-domains (only those with include_in_all=True)
  mode       -- operation: "sync", "query", "status", "search", etc.
  params     -- JSON string with mode-specific args: '{"company":"PETR4","limit":5}'
                "" = no params, use function defaults

ZERO-MAINTENANCE DESIGN
-----------------------
Adding a new domain:
  1. Create data_sources/<domain>/__init__.py with MANIFEST + route()
  2. Done. Dispatcher auto-discovers it on next server restart.

Adding a new sub-domain to an existing domain:
  1. Create data_sources/<domain>/<sub_domain>/__init__.py with MANIFEST + route()
  2. Done. Domain router auto-discovers it.

WHY params AS JSON STRING
--------------------------
FastMCP builds the MCP JSON schema from the @tool function signature.
Explicit typed params require editing dispatcher for every new domain param.
JSON string solves this: 4 stable typed params forever, arbitrary domain args
passed as '{"key": "value"}' -- natural for LLMs which already output JSON.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from registry import tool


def _discover_domains() -> dict:
    """Scan data_sources/ for domain packages with MANIFEST + route()."""
    domains: dict = {}
    sources_dir = Path(__file__).resolve().parent

    for item in sorted(sources_dir.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue
        module_path = f"data_sources.{item.name}"
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
        "Execute a data source operation from any registered domain.",
        "",
        "data_source(domain, sub_domain='', mode='', params='')",
        "  params = JSON string: '{\"company\":\"PETR4\",\"limit\":5}'",
        "  sub_domain='all' runs mode on all sub-domains where include_in_all=True",
        "",
    ]
    for domain_name, module in _DOMAINS.items():
        manifest = module.MANIFEST
        has_sub = manifest.get("has_sub_domains", False)
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
def data_source(
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
                    "error": f"params is not valid JSON: {e}. Example: '{{\"company\":\"PETR4\"}}'"}

    domain = domain.strip().lower()
    if domain not in _DOMAINS:
        return {
            "status": "error",
            "error":  f"Unknown domain '{domain}'. Available: {list(_DOMAINS.keys())}",
        }

    module = _DOMAINS[domain]
    return module.route(sub_domain=sub_domain.strip(), mode=mode.strip(), **kwargs)


data_source.__doc__ = _build_docstring()
