"""Module-level state for memory operations.

Isolates the singleton store instance to prevent cross-module reference
divergence and enable clean test resets.
"""
from __future__ import annotations

import threading

_store: "MemoryStore | None" = None
_store_lock = threading.Lock()


def reset_state() -> None:
    """Clear the cached store instance. Call between tests."""
    global _store
    with _store_lock:
        _store = None
