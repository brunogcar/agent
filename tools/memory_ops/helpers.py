"""Shared helpers for memory action handlers.

Contains lazy store loader, MED-05 tag validation, and memory-type guards.
All validation belongs at the tool layer, NOT the backend.
"""
from __future__ import annotations

import re
from typing import Tuple

from core.config import cfg
from core.contracts import fail

import tools.memory_ops.state as state

# ── MED-05: Tag Validation (Input Sanitization) ────────────────────────────
TAG_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.\s-]*$')

# ── Memory Type Validation ─────────────────────────────────────────────────
VALID_MEMORY_TYPES = {"episodic", "semantic", "procedural"}


def _mem() -> "MemoryStore":
    """Lazy import of memory store — avoids slow ChromaDB load at startup.

    [DESIGN] This function is the ONLY entry point to the MemoryStore
    singleton. Actions call it internally; the facade never calls it.
    The janitor action bypasses this entirely.
    """
    with state._store_lock:
        if state._store is None:
            from core.memory_engine import MemoryStore
            state._store = MemoryStore()
        return state._store


def _validate_tags(tags: str, max_count: int = 6) -> Tuple[bool, str]:
    """Validate tags to prevent injection/XSS attacks.

    Args:
        tags: Comma-separated tag string (may be empty).
        max_count: Maximum tags allowed per entry.

    Returns:
        Tuple of (is_valid, error_message). Returns (True, "") if valid.

    Validation rules:
      - Reject dangerous chars: < > " ' ` | newline
      - Each tag must start with letter, contain only letters/numbers/
        hyphens/dots/underscores/spaces
      - Max N tags (from max_count), max cfg.max_tag_length chars each
    """
    if not tags:
        return True, ""  # Empty is fine

    # Reject dangerous characters immediately (including newline)
    danger_list = ['<', '>', '"', "'", '`', '|', '\n']
    for bad_char in danger_list:
        if bad_char in tags:
            return False, f"Tags cannot contain: {bad_char.replace(chr(10), 'newline')}"

    # Split by comma and validate each tag
    parts = [t.strip() for t in re.split(r'[,\s]+', tags) if t.strip()]

    if not parts:
        return False, "No valid tags found"

    if len(parts) > max_count:
        return False, f"Too many tags (max {max_count})"

    for tag in parts:
        if len(tag) > cfg.max_tag_length:
            return False, (
                f"Tag exceeds length limit ({len(tag)} > {cfg.max_tag_length})"
            )
        if not TAG_PATTERN.fullmatch(tag):
            bad_chars = set(tag) - set(
                'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.- '
            )
            return False, f"Tag contains invalid characters: {bad_chars}"

    return True, ""


def _validate_memory_type(memory_type: str) -> Tuple[bool, str]:
    """Fail-fast validation for memory_type parameter.

    The backend silently coerces invalid types to 'semantic'.
    We validate at the tool layer so the LLM gets a clear error.
    """
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        return False, (
            f"Invalid memory_type '{memory_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )
    return True, ""


def _validate_collections(collections) -> Tuple[bool, str]:
    """Reject empty collections list to prevent silent all-collections fallback.

    The backend treats [] as falsy and falls back to ALL_COLLECTIONS.
    We catch this at the tool layer to prevent confusion.
    """
    if collections is not None and len(collections) == 0:
        return False, "collections cannot be empty — omit or pass None for all"
    return True, ""
