"""
skills/dispatcher.py -- Single MCP tool entry point for all skills.

The LLM sees ONE new tool: skill(domain, mode, **params)

DESIGN
------
- Only this file has @tool -- nothing else in skills/ is MCP-visible.
- Each domain lives in skills/<domain>/__init__.py and exports a MANIFEST dict.
- Dispatcher auto-discovers domains at import time by scanning skills/ subfolders.
- Dynamic docstring is built from all manifests so the LLM always has
  accurate, up-to-date examples without manual docstring maintenance.

ADDING A NEW DOMAIN
-------------------
1. Create skills/<new_domain>/__init__.py with MANIFEST dict and route() function.
   Copy skills/b3/__init__.py as a template.
2. That's it. Dispatcher discovers it automatically on next server restart.
   No changes to this file, registry.py, or server.py.

DECISION: **params not explicit keyword args
  Each domain has different parameters. Passing **params lets the dispatcher
  forward any keyword arguments to the domain's route() function, which
  validates them against its own manifest. This avoids a 20-parameter tool
  signature that confuses the LLM with irrelevant options.

DECISION: Dynamic docstring rebuilt at import time (not at call time)
  FastMCP reads the docstring once at startup to register the tool with the
  MCP server. Rebuilding at import time means the docstring is always current
  when the server starts, without any runtime overhead per call.

DECISION: Domains discovered from filesystem, not a hardcoded list
  skills/<name>/__init__.py + MANIFEST key = auto-registered.
  This means adding a domain never requires touching this file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from registry import tool


# ---------------------------------------------------------------------------
# Domain registry -- built once at import time
# ---------------------------------------------------------------------------

def _discover_domains() -> dict[str, Any]:
    """
    Scan skills/ subfolders for domain modules with a MANIFEST dict.
    Returns {domain_name: module} for all discovered domains.

    A valid domain module must:
      1. Live at skills/<name>/__init__.py
      2. Export MANIFEST dict with at least "domain" and "modes" keys
      3. Export route(mode, **params) -> dict function
    """
    domains: dict[str, Any] = {}
    skills_dir = Path(__file__).resolve().parent

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("_") or item.name.startswith("."):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        module_path = f"skills.{item.name}"
        try:
            module = importlib.import_module(module_path)
            manifest = getattr(module, "MANIFEST", None)
            if not manifest or "domain" not in manifest or "modes" not in manifest:
                continue
            if not callable(getattr(module, "route", None)):
                continue
            domain_name = manifest["domain"]
            domains[domain_name] = module
        except Exception as e:
            print(f"[skills/dispatcher] WARNING: failed to load {module_path}: {e}", file=sys.stderr)

    return domains


_DOMAINS: dict[str, Any] = _discover_domains()


# ---------------------------------------------------------------------------
# Dynamic docstring builder
# ---------------------------------------------------------------------------

def _build_docstring() -> str:
    """
    Build the tool docstring from all discovered domain manifests.
    Called once at module import time.
    """
    lines = [
        "Execute a skill from any registered domain.",
        "",
        "skill(domain, mode, **params)",
        "",
        "domain: the skill domain to use",
        "mode:   the operation within that domain",
        "params: domain/mode-specific keyword arguments (see examples below)",
        "",
    ]

    if not _DOMAINS:
        lines.append("No skill domains registered yet.")
        return "\n".join(lines)

    lines.append("AVAILABLE DOMAINS")
    lines.append("-" * 60)

    for domain_name, module in _DOMAINS.items():
        manifest = module.MANIFEST
        lines.append(f"\ndomain=\"{domain_name}\"")
        lines.append(f"  {manifest.get('description', '')}")
        if manifest.get("source"):
            lines.append(f"  Source: {manifest['source']}")
        lines.append(f"  Modes: {', '.join(manifest['modes'].keys())}")
        lines.append("")

        for mode_name, mode_info in manifest["modes"].items():
            lines.append(f"  mode=\"{mode_name}\"")
            lines.append(f"    {mode_info.get('description', '')}")
            if mode_info.get("params"):
                lines.append("    Parameters:")
                for pname, pdesc in mode_info["params"].items():
                    lines.append(f"      {pname}: {pdesc}")
            if mode_info.get("examples"):
                lines.append("    Examples:")
                for ex in mode_info["examples"]:
                    lines.append(f"      {ex}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The single @tool entry point
# ---------------------------------------------------------------------------

@tool
def skill(
    domain:  str,
    mode:    str,
    # ── b3_api / query params ─────────────────────────────────────────────
    ticker:  str  = "",
    files:   str  = "",
    filters: str  = "",
    columns: str  = "",
    limit:   int  = 100,
    # ── b3_api / sync params ──────────────────────────────────────────────
    force:   bool = False,
) -> dict:
    """
    DECISION: explicit typed parameters instead of **kwargs.

    FastMCP serialises **kwargs as a required 'params' property in the JSON
    schema, which forces the LLM to wrap arguments like:
        skill(domain="b3_api", mode="query", params='{"ticker":"PETR4"}')
    instead of the natural:
        skill(domain="b3_api", mode="query", ticker="PETR4")

    By listing all parameters explicitly with defaults, FastMCP generates a
    flat schema the LLM can fill naturally. Parameters unused by a given
    domain/mode are simply ignored by the route() function.

    ADDING A NEW DOMAIN WITH NEW PARAMS: add them here with a default of ""
    or False. The domain's route() function only reads what it needs.

    files/filters/columns accept JSON strings OR comma-separated values.
    The domain route() function parses them internally.
    """
    domain = domain.strip().lower()

    if domain not in _DOMAINS:
        available = list(_DOMAINS.keys())
        return {
            "status": "error",
            "error":  (
                f"Unknown domain '{domain}'. "
                f"Available: {available}. "
                f"Use skill(domain='<name>', mode='status') to check each domain."
            ),
        }

    # Build params dict -- only pass non-empty values so route() defaults work
    import json as _json

    params: dict = {}

    if ticker:
        params["ticker"] = ticker.strip().upper()

    if files:
        # Accept JSON array string OR comma-separated: "Instruments,Trades"
        try:
            parsed = _json.loads(files)
            params["files"] = parsed if isinstance(parsed, list) else [files]
        except (_json.JSONDecodeError, ValueError):
            params["files"] = [f.strip() for f in files.split(",") if f.strip()]

    if filters:
        try:
            params["filters"] = _json.loads(filters)
        except (_json.JSONDecodeError, ValueError):
            pass   # invalid JSON filter -- ignore, route() will use its defaults

    if columns:
        try:
            parsed = _json.loads(columns)
            params["columns"] = parsed if isinstance(parsed, list) else [columns]
        except (_json.JSONDecodeError, ValueError):
            params["columns"] = [c.strip() for c in columns.split(",") if c.strip()]

    if limit != 100:
        params["limit"] = limit

    if force:
        params["force"] = True

    module = _DOMAINS[domain]
    return module.route(mode=mode, **params)


# Set dynamic docstring so FastMCP registers the correct help text
skill.__doc__ = _build_docstring()


# ---------------------------------------------------------------------------
# skills/__init__.py companion
# ---------------------------------------------------------------------------
# (This file is skills/dispatcher.py, not skills/__init__.py.
#  skills/__init__.py should be empty or contain only a package docstring.
#  The dispatcher is a separate module so it can be imported independently
#  without triggering domain discovery.)
