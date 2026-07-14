"""core/config_backend/validators.py — Inline range checks run during Config.__init__.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

DIFFERENT from ``validation.py``:
    - validators.py :: _validate_config(cfg)   — inline range checks, raises
      immediately on bad values, called at END of __init__ (construction-time).
    - validation.py :: validate_config()       — startup checks (paths exist,
      models configured, model_registry entries valid, ROLES check,
      allowed_internal_hosts type check), called by server.py after all
      imports are done.

Both stay — they serve different purposes.

Checks performed here:
    autocode_max_retries > 0
    autocode_max_file_chars > 0
    autocode_graph_timeout >= max(model_registry role timeouts)
    agent_root.is_absolute() + agent_root.exists()
    MAX_MEMORY_BYTES        ∈ [1, 10_000_000]
    MAX_TAGS_PER_ENTRY      ∈ [1, 50]
    MAX_TAG_LENGTH          ∈ [1, 200]
    WEB_MAX_TEXT_CHARS      ∈ [1, 100_000]
    WEB_SNIPPET_CHARS       ∈ [1, 5000]
    WEB_MAX_SEARCH_RESULTS  ∈ [1, 50]
    DEEP_RESEARCH_MAX_ITERATIONS            ∈ [1, 50]
    DEEP_RESEARCH_COMPLETENESS_THRESHOLD    ∈ (0, 100]
    DEEP_RESEARCH_MAX_API_CALLS             ∈ [0, 100]
    DEEP_RESEARCH_MAX_BROWSER_ACTIONS       ∈ [0, 50]
    DEEP_RESEARCH_TIMEOUT_SECONDS           ∈ [1, 3600]
    DEEP_RESEARCH_CONVERGENCE_THRESHOLD     ∈ (0, 1]
    TAVILY_TIMEOUT           ∈ [1, 300]
    CLI_MAX_COMMAND_LENGTH   ∈ [1, 50_000)
    CLI_MAX_ARGUMENTS        ∈ [1, 100]
    FILE_MAX_READ_CHARS      ∈ [1, 1_000_000]
    MAX_CONTEXT_TOKENS       ∈ [1000, 100_000]
"""

from __future__ import annotations


def _validate_config(cfg) -> None:
    """Run inline range/existence checks. Raises ValueError/FileNotFoundError on failure.

    Called as the LAST step of Config.__init__ (after all _init_* builders
    have populated attributes). Survives ``python -O`` via explicit raise.
    """

    # -- Existing validations (survive python -O via explicit raise) --
    if cfg.autocode_max_retries <= 0:
        raise ValueError("AUTOCODE_MAX_RETRIES must be > 0")
    if cfg.autocode_max_file_chars <= 0:
        raise ValueError("AUTOCODE_MAX_FILE_CHARS must be > 0")

    # Use max timeout from ALL roles in model_registry, not just 3 hardcoded ones
    _all_timeouts = [r["timeout"] for r in cfg.model_registry.values()]
    if cfg.autocode_graph_timeout < max(_all_timeouts):
        raise ValueError("AUTOCODE_GRAPH_TIMEOUT must be >= max(node timeouts)")

    if not cfg.agent_root.is_absolute():
        raise ValueError("AGENT_ROOT must be an absolute path")
    if not cfg.agent_root.exists():
        raise FileNotFoundError(f"AGENT_ROOT not found: {cfg.agent_root}")

    # P2: Validate all new tool limits
    if not (1 <= cfg.memory_max_entry_bytes <= 10_000_000):
        raise ValueError(f"MAX_MEMORY_BYTES must be 1-10000000, got {cfg.memory_max_entry_bytes}")
    if not (1 <= cfg.max_tags_per_entry <= 50):
        raise ValueError(f"MAX_TAGS_PER_ENTRY must be 1-50, got {cfg.max_tags_per_entry}")
    if not (1 <= cfg.max_tag_length <= 200):
        raise ValueError(f"MAX_TAG_LENGTH must be 1-200, got {cfg.max_tag_length}")
    if not (1 <= cfg.web_max_text_chars <= 100_000):
        raise ValueError(f"WEB_MAX_TEXT_CHARS must be 1-100000, got {cfg.web_max_text_chars}")
    if not (1 <= cfg.web_snippet_chars <= 5000):
        raise ValueError(f"WEB_SNIPPET_CHARS must be 1-5000, got {cfg.web_snippet_chars}")
    if not (1 <= cfg.web_max_search_results <= 50):
        raise ValueError(f"WEB_MAX_SEARCH_RESULTS must be 1-50, got {cfg.web_max_search_results}")
    if not (1 <= cfg.deep_research_max_iterations <= 50):
        raise ValueError(f"DEEP_RESEARCH_MAX_ITERATIONS must be 1-50, got {cfg.deep_research_max_iterations}")
    if not (0 < cfg.deep_research_completeness_threshold <= 100):
        raise ValueError(f"DEEP_RESEARCH_COMPLETENESS_THRESHOLD must be 0-100, got {cfg.deep_research_completeness_threshold}")
    if not (0 <= cfg.deep_research_max_api_calls <= 100):
        raise ValueError(f"DEEP_RESEARCH_MAX_API_CALLS must be 0-100, got {cfg.deep_research_max_api_calls}")
    if not (0 <= cfg.deep_research_max_browser_actions <= 50):
        raise ValueError(f"DEEP_RESEARCH_MAX_BROWSER_ACTIONS must be 0-50, got {cfg.deep_research_max_browser_actions}")
    if not (1 <= cfg.deep_research_timeout_seconds <= 3600):
        raise ValueError(f"DEEP_RESEARCH_TIMEOUT_SECONDS must be 1-3600, got {cfg.deep_research_timeout_seconds}")

    # DEEP_RESEARCH_CONVERGENCE_THRESHOLD — was inline in services pre-v1.0
    if not (0 < cfg.deep_research_convergence_threshold <= 1):
        raise ValueError(
            f"DEEP_RESEARCH_CONVERGENCE_THRESHOLD must be 0-1, got {cfg.deep_research_convergence_threshold}"
        )

    if not (1 <= cfg.tavily_timeout <= 300):
        raise ValueError(f"TAVILY_TIMEOUT must be 1-300, got {cfg.tavily_timeout}")
    if not (1 <= cfg.cli_max_command_chars < 50_000):
        raise ValueError(f"CLI_MAX_COMMAND_LENGTH must be 1-49999, got {cfg.cli_max_command_chars}")
    if not (1 <= cfg.cli_max_arguments <= 100):
        raise ValueError(f"CLI_MAX_ARGUMENTS must be 1-100, got {cfg.cli_max_arguments}")
    if not (1 <= cfg.file_max_read_chars <= 1_000_000):
        raise ValueError(f"FILE_MAX_READ_CHARS must be 1-1000000, got {cfg.file_max_read_chars}")

    # MAX_CONTEXT_TOKENS — was inline in memory pre-v1.0
    if not (1000 <= cfg.max_context_tokens <= 100000):
        raise ValueError(
            f"MAX_CONTEXT_TOKENS must be 1000-100000, got {cfg.max_context_tokens}"
        )
