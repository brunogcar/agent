"""
Config validation on startup - fail fast with clear errors.
"""

from __future__ import annotations

from core.config import cfg
from core.tracer import tracer

def validate_config() -> None:
    """
    Validate all critical configuration at startup.
    Raises RuntimeError with clear message if validation fails.
    """
    errors = []

    # -- Paths must exist --
    critical_paths = [
        ("agent_root", cfg.agent_root),
        ("workspace_root", cfg.workspace_root),
        ("memory_root", cfg.memory_root),
        ("memory_chroma_path", cfg.memory_chroma_path),
        ("workspace_autocode", cfg.workspace_autocode),
        ("workspace_index", cfg.workspace_index),
        ("log_path", cfg.log_path),
    ]

    for name, path in critical_paths:
        if not path.exists():
            errors.append(f"{name} does not exist: {path}")

    # -- Models must be configured --
    if not cfg.planner_model:
        errors.append("PLANNER_MODEL is required in .env")
    if not cfg.executor_model:
        errors.append("EXECUTOR_MODEL is required in .env")
    if not cfg.router_model:
        errors.append("ROUTER_MODEL is required in .env")

    # -- Timeouts must be positive --
    timeouts = [
        ("sandbox_timeout", cfg.sandbox_timeout),
        ("execution_timeout", cfg.execution_timeout),
        ("planner_timeout", cfg.planner_timeout),
        ("router_timeout", cfg.router_timeout),
        ("autocode_graph_timeout", cfg.autocode_graph_timeout),
    ]

    for name, value in timeouts:
        if value <= 0:
            errors.append(f"{name} must be > 0 (got: {value})")

    # -- Max retries must be positive --
    if cfg.autocode_max_retries <= 0:
        errors.append(f"autocode_max_retries must be > 0 (got: {cfg.autocode_max_retries})")
    if cfg.autocode_max_file_chars <= 0:
        errors.append(f"autocode_max_file_chars must be > 0 (got: {cfg.autocode_max_file_chars})")

    # -- LM Studio URL must be valid --
    if not cfg.lm_studio_base_url.startswith(("http://", "https://")):
        errors.append(f"lm_studio_base_url must be a valid URL: {cfg.lm_studio_base_url}")

    # -- model_registry entries must have non-empty model strings (Bug #17) --
    # Catches misconfigured .env where a *_MODEL var is set but resolves to
    # an empty string (e.g., "EXECUTOR_MODEL=" with no value).
    for role_name, entry in cfg.model_registry.items():
        if not entry.get("model"):
            errors.append(
                f"model_registry['{role_name}'] has empty 'model' — "
                f"check the corresponding *_MODEL env var in .env"
            )
        if not entry.get("provider"):
            errors.append(
                f"model_registry['{role_name}'] has empty 'provider'"
            )
        if entry.get("timeout", 0) <= 0:
            errors.append(
                f"model_registry['{role_name}'] has invalid 'timeout' "
                f"(got: {entry.get('timeout')})"
            )

    # -- All agent roles must have a model_registry entry (Bug #17) --
    # Catches typos in role configs (e.g., llm_role='cod' instead of 'code')
    # at startup instead of at first dispatch call.
    # Skip if tools.agent_ops isn't importable yet (early validation passes).
    try:
        from tools.agent_ops import ROLES
        for role_name, role_data in ROLES.items():
            llm_role = role_data.get("role_config", {}).get("llm_role", "")
            if llm_role and llm_role not in cfg.model_registry:
                # Opt-in roles (e.g., consultor when CONSULTOR_MODEL is unset)
                # are expected to be absent — warn but don't error.
                # Required roles with missing entries are errors.
                if role_name == "consultor":
                    continue  # opt-in, skip
                errors.append(
                    f"Role '{role_name}' has llm_role='{llm_role}' which is not "
                    f"in model_registry. Valid: {sorted(cfg.model_registry.keys())}"
                )
    except ImportError:
        pass  # tools.agent_ops not importable yet — skip ROLES check

    # -- allowed_internal_hosts must be a frozenset of strings (Bug #17) --
    # Catches malformed ALLOWED_INTERNAL_HOSTS env var (e.g., non-string entries
    # after splitting). The frozenset comprehension in config.py filters empty
    # strings, but a non-string value would slip through.
    if not isinstance(cfg.allowed_internal_hosts, (frozenset, set, list)):
        errors.append(
            f"allowed_internal_hosts must be a set/list, got "
            f"{type(cfg.allowed_internal_hosts).__name__}"
        )
    else:
        for host in cfg.allowed_internal_hosts:
            if not isinstance(host, str) or not host:
                errors.append(
                    f"allowed_internal_hosts contains invalid entry: {host!r}"
                )

    # -- Raise if any errors --
    if errors:
        error_msg = "Config validation failed:\n  - " + "\n  - ".join(errors)
        tracer.error("startup", "config_validation", "Startup config check failed", extra={"errors": errors})
        raise RuntimeError(error_msg)

    tracer.step("startup", "config_validation", "All config checks passed")