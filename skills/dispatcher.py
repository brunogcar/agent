"""skills/dispatcher.py — Single MCP @tool entry point for all skills.

ARCHITECTURE
------------
skill(domain, sub_domain, mode, params)

Skills are higher-level analytical views that COMBINE multiple data sources
with domain reasoning. They sit on top of data_sources/ (raw data) and are
read-only (no sync — they assume data is already synced).

  domain     -- top-level domain: "cvm", "b3", etc.
  sub_domain -- skill within domain: "shareholders", "dividends", etc.
                "" or omitted = auto-select if only one skill exists
  mode       -- operation: "shareholders", "annual", "summary", etc.
  params     -- JSON string with mode-specific args: '{"company":"PETR4","periods":5}'

ZERO-MAINTENANCE DESIGN (mirrors data_sources/dispatcher.py)
------------------------------------------------------------
Adding a new domain:
  1. Create skills/<domain>/__init__.py with MANIFEST + route()
  2. Done. Dispatcher auto-discovers it on next server restart.

Adding a new skill to an existing domain:
  1. Create skills/<domain>/<skill>/__init__.py with MANIFEST + route()
  2. Done. Domain router auto-discovers it.

SKILLS vs DATA_SOURCES
----------------------
data_sources = raw data ingestion + query (sync, status, query modes)
skills       = analytical views that combine data sources + reasoning
               (no sync — read-only over already-synced data)

Example:
  data_source(domain="cvm", sub_domain="fre", mode="shareholders")  -- raw FRE query
  skill(domain="cvm", sub_domain="shareholders", mode="shareholders") -- combines FRE + DFP
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
            print(f"[skills] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return domains


_DOMAINS: dict = _discover_domains()


def _build_docstring() -> str:
    lines = [
        "Execute a skill (analytical view) from any registered domain.",
        "",
        "skill(domain, sub_domain='', mode='', params='')",
        "  params = JSON string: '{\"company\":\"PETR4\",\"periods\":5}'",
        "  sub_domain='all' runs mode on all skills where include_in_all=True",
        "",
        "Skills combine multiple data sources with domain reasoning.",
        "They are read-only (no sync) — assume data is already synced.",
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
                    tag = " [all]" if m_info.get("include_in_all") else ""
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
                    "error": f"params is not valid JSON: {e}. Example: '{{\"company\":\"PETR4\"}}'"}

    domain = domain.strip().lower()
    if domain not in _DOMAINS:
        return {
            "status": "error",
            "error":  f"Unknown domain '{domain}'. Available: {list(_DOMAINS.keys())}",
        }

    module = _DOMAINS[domain]
    return module.route(sub_domain=sub_domain.strip(), mode=mode.strip(), **kwargs)


skill.__doc__ = _build_docstring()
