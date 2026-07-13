"""tools/memory_ops/helpers.py — Shared helpers for memory action handlers.
v1.2: Tag splitting fixed to comma-only (multi-word tags preserved).


[DESIGN] KEY DECISIONS — read before modifying:

  1. SINGLETON CONSTRAINT: _mem() MUST return the same MemoryStore as
     core/memory_engine.memory.
     CORRECT: from core.memory_engine import memory as _singleton
              state._store = _singleton
     WRONG:   from core.memory_engine import MemoryStore
              state._store = MemoryStore()
     If _mem() creates a NEW MemoryStore(): two separate _hash_cache sets -> dedup broken
     between tool and workflow writes; two separate _write_lock instances -> TOCTOU fix broken.
     [v1.3 FIX] Previously _mem() called MemoryStore() creating a second instance.
     Fixed to use the module-level singleton from core.memory_engine.

  2. TAG SPLITTING is comma-only (v1.2+). Spaces within a tag are PRESERVED.
     "machine learning, python" -> ["machine learning", "python"] (correct)
     Do NOT revert to splitting on whitespace.

  3. TAG VALIDATION uses DIFFERENT LIMITS for write vs read (MED-05 compliance, keep both):
     store: cfg.max_tags_per_entry (default 6) — strict, write time
     recall filter: hardcoded 10 — relaxed, read-only

  4. collections=[] is REJECTED (v1.1+), collections=None searches ALL collections.
     _validate_collections() explicitly rejects empty lists:
     "collections cannot be empty — omit or pass None for all".
     Empty list = error, NOT all-collections fallback. Do NOT change this to a
     falsy fallback — it masks caller bugs.

  5. JANITOR BYPASS: janitor.py MUST NEVER import this file or call _mem().
"""
from __future__ import annotations

import re
from typing import Tuple

import tools.memory_ops.state as state
from core.config import cfg

def _mem() -> "MemoryStore":
    """Lazy import of memory store — avoids slow ChromaDB load at startup.

    [v1.3 FIX] Use the module-level singleton from core.memory_engine instead of
    creating a new MemoryStore(). Two separate instances would have separate
    _hash_cache sets (dedup broken between tool and workflow writes) and separate
    _write_lock instances (TOCTOU fix in write_ops.py broken). See [DESIGN] block.
    """
    with state._store_lock:
        if state._store is None:
            from core.memory_engine import memory as _singleton
            state._store = _singleton
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
