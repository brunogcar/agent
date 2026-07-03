"""tools/memory_ops/helpers.py — Shared helpers for memory action handlers.
v1.2: Tag splitting fixed to comma-only (multi-word tags preserved).
"""
from __future__ import annotations

import re
from typing import Tuple

import tools.memory_ops.state as state
from core.config import cfg

def _mem() -> "MemoryStore":
    """Lazy import of memory store — avoids slow ChromaDB load at startup."""
    with state._store_lock:
        if state._store is None:
            from core.memory_engine import MemoryStore
            state._store = MemoryStore()
        return state._store

def _validate_tags(tags: str, max_count: int = 6) -> Tuple[bool, str]:
    """MED-05 tag validation."""
    if not tags:
        return True, ""

    danger_list = {"<", ">", "\"", "'", "`", "|", "\n", "\r", "\t"}
    for ch in danger_list:
        if ch in tags:
            return False, f"Tags cannot contain: {ch!r}"

    parts = [t.strip() for t in tags.split(",") if t.strip()]
    if not parts:
        return False, "No valid tags found"

    if len(parts) > max_count:
        return False, f"Too many tags ({len(parts)} > {max_count})"

    for p in parts:
        if len(p) > cfg.max_tag_length:
            return False, f"Tag '{p[:20]}...' exceeds length limit ({cfg.max_tag_length})"
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_.\s-]*$', p):
            return False, f"Tag '{p}' contains invalid characters"

    return True, ""

def _validate_memory_type(memory_type: str) -> Tuple[bool, str]:
    """Reject invalid memory_type before backend silently coerces to 'semantic'."""
    valid = {"episodic", "semantic", "procedural"}
    if memory_type and memory_type not in valid:
        return False, f"Invalid memory_type '{memory_type}'. Must be one of: {', '.join(sorted(valid))}"
    return True, ""

def _validate_collections(collections) -> Tuple[bool, str]:
    """Reject empty collections list to prevent silent all-collections fallback.
    v1.1: Also rejects non-list types (e.g., strings) to prevent TypeError."""
    if collections is not None:
        if not isinstance(collections, list):
            return False, f"collections must be a list, got {type(collections).__name__}"
        if len(collections) == 0:
            return False, "collections cannot be empty — omit or pass None for all"
    return True, ""
