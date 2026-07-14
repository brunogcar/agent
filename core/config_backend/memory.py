"""core/config_backend/memory.py — Initialize memory tuning, diversity, context budgeting.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    Memory tuning:
        MEMORY_DELETE_THRESHOLD  — default 0.4 (float)
        MEMORY_DECAY_DAYS        — default 30
        MEMORY_TOP_K             — default 5

    Memory Diversity (Phase 6):
        DIVERSITY_DISTANCE_THRESHOLD  — default 0.12 (float)
        ARCHIVE_AGE_DAYS              — default 30
        PURGE_AGE_DAYS                — default 90

    Context Budgeting (Phase 5):
        MAX_CONTEXT_TOKENS  — default 8000
        [BUGFIX-5] Parsing errors raise here; range check (1000-100000)
        lives in validators.py::_validate_config.
"""

from __future__ import annotations

import os


def _init_memory(cfg) -> None:
    """Initialize memory tuning, diversity, and context budget attributes."""

    # -- Memory tuning -----------------------------------------------------
    cfg.memory_delete_threshold = float(os.getenv("MEMORY_DELETE_THRESHOLD", "0.4"))
    cfg.memory_decay_days = int(os.getenv("MEMORY_DECAY_DAYS", "30"))
    cfg.memory_top_k = int(os.getenv("MEMORY_TOP_K", "5"))

    # -- Memory Diversity (Phase 6) ----------------------------------------
    cfg.diversity_distance_threshold = float(os.getenv("DIVERSITY_DISTANCE_THRESHOLD", "0.12"))
    cfg.archive_age_days = int(os.getenv("ARCHIVE_AGE_DAYS", "30"))
    cfg.purge_age_days = int(os.getenv("PURGE_AGE_DAYS", "90"))

    # -- Context Budgeting (Phase 5) ---------------------------------------
    # Max tokens for the input context window (leaves room for output)
    # [BUGFIX-5] Validated: prevents 0/negative values that would silently
    # truncate all context to nothing in agent_tool.py.
    _raw_max_context = os.getenv("MAX_CONTEXT_TOKENS", "8000")
    try:
        cfg.max_context_tokens = int(_raw_max_context)
    except ValueError:
        raise ValueError(f"MAX_CONTEXT_TOKENS must be an integer, got '{_raw_max_context}'")
    # Range check (1000-100000) moved to validators.py::_validate_config.
