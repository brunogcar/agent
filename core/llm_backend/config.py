"""
core/llm_backend/config.py — Role-based LLM configuration.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from core.config import cfg

@dataclass
class RoleConfig:
    model:       str
    provider:    str   = "lmstudio"
    timeout:     int   = 60
    temperature: float = 0.2
    max_tokens:  int   = 1024

def _build_role_configs() -> dict[str, RoleConfig]:
    roles: dict[str, RoleConfig] = {}
    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "vision":    {"temperature": 0.1, "max_tokens": 1024, "timeout": 60},
        "summarize": {"temperature": 0.1, "max_tokens": 512,  "timeout": 60},
        "extract":   {"temperature": 0.0, "max_tokens": 512,  "timeout": 60},
        "classify":  {"temperature": 0.0, "max_tokens": 64,   "timeout": 15},
        "research":  {"temperature": 0.2, "max_tokens": 1024, "timeout": 120},
        "critique":  {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
        "analyze":   {"temperature": 0.1, "max_tokens": 1024, "timeout": 90},
        "code":      {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "review":    {"temperature": 0.2, "max_tokens": 768,  "timeout": 90},
        "consultor": {"temperature": 0.2, "max_tokens": 1024, "timeout": 60},
    }

    executor_model = cfg.model_registry.get("executor", {}).get("model", cfg.executor_model)

    for role, d in defaults.items():
        reg_entry = cfg.model_registry.get(role, {})
        
        # Vision falls back to cfg.vision_model, not executor_model
        if role == "vision":
            model = reg_entry.get("model", cfg.vision_model or executor_model)
        else:
            model = reg_entry.get("model", executor_model)
            
        timeout   = reg_entry.get("timeout", d["timeout"])
        
        roles[role] = RoleConfig(
            model       = model,
            provider    = reg_entry.get( "provider ",  "lmstudio "),  # Read provider from config.py
            timeout     = timeout,
            temperature = d["temperature"],
            max_tokens  = d["max_tokens"],
        )
    return roles