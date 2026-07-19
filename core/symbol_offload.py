"""core/symbol_offload.py — TencentDB-inspired symbol offloading.

Offloads verbose state fields to per-run files on disk, replacing them
in-state with compact SymbolRef dicts. Nodes that need full data drill
down via the file path.

This complements chonkie (within-field compression) with cross-field
context management. Chonkie compresses a single field's text; symbol
offloading moves the full content to a file and replaces it with a
short reference + summary.

Usage:
    from core.symbol_offload import offload_to_file, drill_down, is_symbol_ref

    # Offload verbose debug_history to a file
    ref = offload_to_file(trace_id, "debug_history", debug_history_list)
    # ref = {"_symbol_ref": "debug_history", "_symbol_file": "/path/to/file.json",
    #        "_symbol_summary": "5 entries (3 failed, 2 passed)", "_symbol_size": 4523}

    # Later, drill down to get the full content
    if is_symbol_ref(ref):
        full_history = drill_down(ref)

Inspired by: https://github.com/TencentCloud/TencentDB-Agent-Memory
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from core.config import cfg


def _symbol_dir(trace_id: str) -> Path:
    """Return the per-trace symbol offload directory."""
    d = cfg.workspace_root / ".symbols" / trace_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def offload_to_file(
    trace_id: str,
    field_name: str,
    content: Any,
    summary: str = "",
) -> dict:
    """Offload content to a per-trace file, return a compact SymbolRef.

    Args:
        trace_id: The workflow's trace ID (used for the file path).
        field_name: Name of the state field being offloaded (e.g. "debug_history").
        content: The full content to offload (list, dict, str — must be JSON-serializable).
        summary: Optional one-line summary. If empty, auto-generated from content.

    Returns:
        A SymbolRef dict with:
            _symbol_ref: the field name
            _symbol_file: absolute path to the offloaded file
            _symbol_summary: one-line summary of the content
            _symbol_size: original content size in bytes (approx)
    """
    # Sanitize field_name for filename
    safe_name = field_name.replace("/", "_").replace("\\", "_")
    file_path = _symbol_dir(trace_id) / f"{safe_name}.json"

    # Write content to file
    serialized = json.dumps(content, ensure_ascii=False, default=str)
    file_path.write_text(serialized, encoding="utf-8")

    # Auto-generate summary if not provided
    if not summary:
        summary = _auto_summary(content)

    return {
        "_symbol_ref": field_name,
        "_symbol_file": str(file_path),
        "_symbol_summary": summary,
        "_symbol_size": len(serialized.encode("utf-8")),
    }


def _auto_summary(content: Any) -> str:
    """Generate a one-line summary from content."""
    if isinstance(content, list):
        count = len(content)
        if count == 0:
            return "empty list"
        # Try to summarize list entries
        if isinstance(content[0], dict):
            # Check for common keys
            if "tests_passed" in content[0]:
                passed = sum(1 for e in content if e.get("tests_passed"))
                failed = count - passed
                return f"{count} entries ({passed} passed, {failed} failed)"
            if "rule" in content[0]:
                return f"{count} rules"
            if "text" in content[0]:
                return f"{count} text entries"
            return f"{count} entries"
        return f"{count} items"
    if isinstance(content, dict):
        return f"{len(content)} keys"
    if isinstance(content, str):
        return f"{len(content)} chars"
    return str(type(content).__name__)


def drill_down(symbol_ref: dict) -> Optional[Any]:
    """Read the full content from the offloaded file.

    Args:
        symbol_ref: A SymbolRef dict from offload_to_file().

    Returns:
        The original content, or None if the file doesn't exist.
    """
    file_path = symbol_ref.get("_symbol_file", "")
    if not file_path:
        return None
    p = Path(file_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_symbol_ref(value: Any) -> bool:
    """Check if a value is a SymbolRef dict."""
    return (
        isinstance(value, dict)
        and "_symbol_ref" in value
        and "_symbol_file" in value
    )
