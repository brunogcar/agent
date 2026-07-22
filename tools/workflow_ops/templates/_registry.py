"""tools/workflow_ops/templates/_registry.py — Template loader + registry.

Scans the templates/ directory at import time for *.json files, loads each
into a dict, and exposes two accessors:
  - get_template(name) -> dict | None — single-template lookup
  - list_templates() -> list[dict]    — all templates as a list

Template JSON format (see bug-fix.json for the canonical example):
  {
    "name":         "bug-fix",                  # unique key
    "type":         "autocode",                 # workflow type
    "description":  "Fix a bug ...",            # human-readable
    "params":       {"mode": "fix_error", ...}, # pre-set params
    "required":     ["target_file", "error_msg"] # params caller must still provide
  }

Each loaded dict is augmented with a `_source_file` key (basename of the
JSON file) for debugging.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_TEMPLATES_DIR = Path(__file__).parent


def _load_templates() -> dict:
    """Scan the templates directory for *.json files and load them.

    Returns a dict keyed by template `name` field. If two JSON files declare
    the same `name`, the last one loaded (alphabetical filename order) wins —
    logged via a warning but not fatal.
    """
    loaded: dict = {}
    for json_path in sorted(_TEMPLATES_DIR.glob("*.json")):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                tmpl = json.load(f)
        except Exception:
            # Skip malformed templates silently — they show up as "missing"
            # in get_template() lookups. Production code should log this.
            continue
        if not isinstance(tmpl, dict):
            continue
        # Inject source-file basename for debugging.
        tmpl["_source_file"] = json_path.name
        # Key by `name` field; fall back to filename stem if `name` missing.
        key = tmpl.get("name") or json_path.stem
        loaded[key] = tmpl
    return loaded


# Module-level cache — loaded once at import time.
TEMPLATES: dict = _load_templates()


def get_template(name: str) -> Optional[dict]:
    """Look up a template by name. Returns the template dict or None.

    Args:
        name: Template name (matches the `name` field in the JSON file).

    Returns:
        Template dict with keys: name, type, description, params, required,
        _source_file. None if no template with that name exists.
    """
    if not name:
        return None
    return TEMPLATES.get(name)


def list_templates() -> list:
    """Return all loaded templates as a list of dicts.

    The order is alphabetical by template `name` (dict iteration order is
    insertion order in Python 3.7+, and _load_templates sorts files
    alphabetically before loading).
    """
    return list(TEMPLATES.values())
