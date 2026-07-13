"""core/llm_backend/config.py -- LLM role configuration builder.

Builds RoleConfig objects from cfg.model_registry and hardcoded defaults.


[DESIGN] KEY DECISIONS — read before modifying:

  1. SINGLE FALLBACK CHAIN — ALL roles fall back to planner_model.
     _build_role_configs() line 58: model = reg_entry.get("model", cfg.planner_model).
     If a role's model is not set in model_registry (e.g., consultor disabled),
     it falls back to planner_model — NOT to a group-specific model.
     Each role has its own env var (EXECUTOR_MODEL, ROUTER_MODEL, etc.);
     if unset, the model string is empty and the role is skipped (not in ROLE_CONFIGS).

  2. temperature and max_tokens ARE HARDCODED in _defaults, NOT from .env.
     Only model, provider, base_url, and timeout come from .env.
     Verified: planner temp=0.2/32768tok, executor temp=0.0/16384tok.
     Full table: docs/core/LLM.md

  3. budget_chars in agent_ops/roles/*.py IS NOT max_tokens * 4.
     budget_chars = max INPUT CONTEXT chars. max_tokens = max OUTPUT tokens.
     Different questions, different numbers. DO NOT derive one from the other.

  4. EXECUTOR_TIMEOUT is the correct env var (not EXECUTION_TIMEOUT).
     cfg.execution_timeout reads from model_registry["executor"]["timeout"]
     which uses _make_entry("EXECUTOR_TIMEOUT", 120). The attribute is named
     execution_timeout but the env var is EXECUTOR_TIMEOUT — do not "fix" this
     mismatch; it is intentional (execution_timeout is the derived attribute,
     EXECUTOR_TIMEOUT is the env var source).

  5. consultor role is CONDITIONALLY registered — only if CONSULTOR_MODEL is set.
     _build_role_configs() skips roles not in model_registry. If consultor_mod
     is empty, consultor is not added to ROLE_CONFIGS. Calling
     llm.complete(role='consultor') when unconfigured falls back via _get_role().
"""
from __future__ import annotations
from dataclasses import dataclass
from core.config import cfg
from core.tracer import tracer

@dataclass(frozen=True)
class RoleConfig:
    model: str
    provider: str
    timeout: int
    temperature: float
    max_tokens: int

# Default behavior per role (temperature, max_tokens only).
# Timeout comes from cfg.model_registry (single source of truth in core/config.py).
# Model and provider come from cfg.model_registry.
_defaults: dict[str, dict] = {
    # Group mains
    "planner": {"temperature": 0.2, "max_tokens": 32768},
    "executor": {"temperature": 0.0, "max_tokens": 16384},
    "router": {"temperature": 0.0, "max_tokens": 512},
    "vision": {"temperature": 0.2, "max_tokens": 4096},
    "consultor": {"temperature": 0.2, "max_tokens": 4096},
    # Sub-roles to executor
    "summarize": {"temperature": 0.2, "max_tokens": 8192},
    "extract": {"temperature": 0.0, "max_tokens": 4096},
    "research": {"temperature": 0.2, "max_tokens": 16384},
    "critique": {"temperature": 0.3, "max_tokens": 8192},
    "analyze": {"temperature": 0.2, "max_tokens": 16384},
    "code": {"temperature": 0.0, "max_tokens": 16384},
    "review": {"temperature": 0.2, "max_tokens": 8192},
    # Sub-roles to router
    "classify": {"temperature": 0.0, "max_tokens": 256},
    "route": {"temperature": 0.0, "max_tokens": 256},
    # NEW: Autonomous maintenance roles
    "refactor": {"temperature": 0.0, "max_tokens": 16384},
    "test": {"temperature": 0.0, "max_tokens": 16384},
    "document": {"temperature": 0.2, "max_tokens": 16384},
}

def _build_role_configs() -> dict[str, RoleConfig]:
    """Build RoleConfig for every role from cfg.model_registry.
    Skips roles not present in model_registry (e.g., disabled consultor).
    Falls back to planner_model if a role is not in registry.
    """
    roles: dict[str, RoleConfig] = {}

    for role, d in _defaults.items():
        reg_entry = cfg.model_registry.get(role)
        if reg_entry is None:
            # Role not configured (e.g., consultor disabled) — skip it
            continue

        model = reg_entry.get("model", cfg.planner_model)
        provider = reg_entry.get("provider", "lmstudio")
        # Timeout is the single source of truth from core/config.py
        timeout = reg_entry["timeout"]

        roles[role] = RoleConfig(
            model=model,
            provider=provider,
            timeout=timeout,
            temperature=d["temperature"],
            max_tokens=d["max_tokens"],
        )
    return roles

# Module-level role configs — built once at import time
ROLE_CONFIGS: dict[str, RoleConfig] = _build_role_configs()


def set_role_model(role: str, model: str) -> str:
    """Temporarily set model for a role. Returns previous model.

    Used by Benchmark to override models for a run. Restores after run.
    """
    if role not in ROLE_CONFIGS:
        return ""
    old = ROLE_CONFIGS[role].model
    old_cfg = ROLE_CONFIGS[role]
    ROLE_CONFIGS[role] = RoleConfig(
        model=model,
        provider=old_cfg.provider,
        timeout=old_cfg.timeout,
        temperature=old_cfg.temperature,
        max_tokens=old_cfg.max_tokens,
    )
    return old
