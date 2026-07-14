"""core/config_backend/limits.py — Initialize tool & system limits (P2: centralized magic numbers).

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    Memory Tool Limits:
        MAX_MEMORY_BYTES      — default 50000 (50KB per entry; renamed to
                                cfg.memory_max_entry_bytes per D1 Option B consensus)
        MAX_TAGS_PER_ENTRY   — default 6
        MAX_TAG_LENGTH       — default 50

    Web Tool Limits:
        WEB_MAX_TEXT_CHARS       — default 8000 (conservative; ~2-3k tokens)
        WEB_SNIPPET_CHARS        — default 300
        WEB_MAX_SEARCH_RESULTS   — default 10

    CLI Tool Limits:
        CLI_MAX_COMMAND_LENGTH   — default 4096 (matches typical terminal buffer;
                                    renamed to cfg.cli_max_command_chars)
        CLI_MAX_ARGUMENTS        — default 20

    File Tool Limits:
        FILE_MAX_READ_CHARS      — default 50000

All ranges are validated in validators.py::_validate_config.
"""

from __future__ import annotations

import os


def _init_limits(cfg) -> None:
    """Initialize memory/web/CLI/file tool limits from env vars."""

    # -- Tool & System Limits (P2: Centralized Magic Numbers) --------------

    # Memory Tool Limits
    # Renamed from max_memory_bytes to memory_max_entry_bytes (D1 Option B consensus)
    # to clarify this is per-entry, not total storage limit
    cfg.memory_max_entry_bytes = int(os.getenv("MAX_MEMORY_BYTES", "50000"))  # 50KB per entry
    cfg.max_tags_per_entry = int(os.getenv("MAX_TAGS_PER_ENTRY", "6"))
    cfg.max_tag_length = int(os.getenv("MAX_TAG_LENGTH", "50"))

    # Web Tool Limits
    # NOTE: 8000 chars (~2-3k tokens) is a conservative default to prevent
    # context overflow in existing workflows that depend on this value.
    # Override in .env if you need larger pages.
    cfg.web_max_text_chars = int(os.getenv("WEB_MAX_TEXT_CHARS", "8000"))
    cfg.web_snippet_chars = int(os.getenv("WEB_SNIPPET_CHARS", "300"))
    cfg.web_max_search_results = int(os.getenv("WEB_MAX_SEARCH_RESULTS", "10"))

    # CLI Tool Limits
    # 4096 matches typical terminal buffer sizes; 1024 was too restrictive
    # for real-world commands like `git log --oneline` or complex pipelines.
    cfg.cli_max_command_chars = int(os.getenv("CLI_MAX_COMMAND_LENGTH", "4096"))
    cfg.cli_max_arguments = int(os.getenv("CLI_MAX_ARGUMENTS", "20"))

    # File Tool Limits
    cfg.file_max_read_chars = int(os.getenv("FILE_MAX_READ_CHARS", "50000"))
