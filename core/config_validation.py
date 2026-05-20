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

    # -- Raise if any errors --
    if errors:
        error_msg = "Config validation failed:\n  - " + "\n  - ".join(errors)
        tracer.error("config_validation", "Startup config check failed", extra={"errors": errors})
        raise RuntimeError(error_msg)

    tracer.step("config_validation", "All config checks passed")