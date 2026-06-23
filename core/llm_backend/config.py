"""core/llm_backend/config.py -- LLM role configuration builder.

Builds RoleConfig objects from cfg.model_registry and hardcoded defaults.
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

# Default behavior per role (temperature, max_tokens, timeout)
# Model and provider come from cfg.model_registry
_defaults: dict[str, dict] = {
    # Group mains
    "planner":   {"temperature": 0.2, "max_tokens": 32768, "timeout": 180},
    "executor":  {"temperature": 0.0, "max_tokens": 16384, "timeout": 120},
    "router":    {"temperature": 0.0, "max_tokens": 512,   "timeout": 15},
    "vision":    {"temperature": 0.2, "max_tokens": 4096,  "timeout": 60},
    "consultor": {"temperature": 0.2, "max_tokens": 4096,  "timeout": 60},
    # Sub-roles to executor
    "summarize": {"temperature": 0.2, "max_tokens": 8192,  "timeout": 60},
    "extract":   {"temperature": 0.0, "max_tokens": 4096,  "timeout": 60},
    "research":  {"temperature": 0.2, "max_tokens": 16384, "timeout": 120},
    "critique":  {"temperature": 0.3, "max_tokens": 8192,  "timeout": 90},
    "analyze":   {"temperature": 0.2, "max_tokens": 16384, "timeout": 90},
    "code":      {"temperature": 0.0, "max_tokens": 16384, "timeout": 120},
    "review":    {"temperature": 0.2, "max_tokens": 8192,  "timeout": 90},
    # Sub-roles to router
    "classify":  {"temperature": 0.0, "max_tokens": 256,   "timeout": 15},
    "route":     {"temperature": 0.0, "max_tokens": 256,   "timeout": 15},
}


def _build_role_configs() -> dict[str, RoleConfig]:
    """Build RoleConfig for every role from cfg.model_registry.
    Falls back to planner_model if a role is not in registry.
    """
    roles: dict[str, RoleConfig] = {}

    for role, d in _defaults.items():
        reg_entry = cfg.model_registry.get(role, {})
        model = reg_entry.get("model", cfg.planner_model)
        provider = reg_entry.get("provider", "lmstudio")
        timeout = reg_entry.get("timeout", d["timeout"])

        roles[role] = RoleConfig(
            model=model,
            provider=provider,
            timeout=timeout,
            temperature=d["temperature"],
            max_tokens=d["max_tokens"],
        )
    return roles

def set_role_model(self, role: str, model: str) -> str:
    """Temporarily set model for a role. Returns previous model. Used by Benchmark to override models for a run. Restores after run."""
    if role not in self._roles:
        return ""
    old = self._roles[role].model
    old_cfg = self._roles[role]
    self._roles[role] = RoleConfig(
        model=model,
        provider=old_cfg.provider,
        timeout=old_cfg.timeout,
        temperature=old_cfg.temperature,
        max_tokens=old_cfg.max_tokens,
    )
    return old