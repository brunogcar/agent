"""Agent role configuration: LLM role mapping, JSON mode flags, context budgets, and fallbacks."""
from __future__ import annotations

# ── Unified role configuration ────────────────────────────────────────────────
# Single source of truth for all role metadata.
# Adding a new role: add entry here, add prompt in prompts.py, done.

ROLE_CONFIG: dict[str, dict] = {
    "classify": {
        "llm_role": "router",
        "json_mode": None,
        "budget_chars": 16000,
        "cacheable": True,
        "fallback_role": "route",  # If classify fails, try route
    },
    "route": {
        "llm_role": "router",
        "json_mode": "prompt",
        "budget_chars": 16000,
        "cacheable": True,
        "fallback_role": None,
    },
    "research": {
        "llm_role": "research",
        "json_mode": None,
        "budget_chars": 128000,
        "cacheable": False,
        "fallback_role": None,
    },
    "summarize": {
        "llm_role": "summarize",
        "json_mode": None,
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": None,
    },
    "extract": {
        "llm_role": "extract",
        "json_mode": "api",
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": None,
    },
    "critique": {
        "llm_role": "critique",
        "json_mode": None,
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": "analyze",  # If critique fails, get analysis instead
    },
    "analyze": {
        "llm_role": "analyze",
        "json_mode": None,
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": None,
    },
    "code": {
        "llm_role": "code",
        "json_mode": "prompt",
        "budget_chars": 128000,
        "cacheable": False,
        "fallback_role": None,
    },
    "review": {
        "llm_role": "review",
        "json_mode": "prompt",
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": None,
    },
    "plan": {
        "llm_role": "planner",
        "json_mode": "prompt",
        "budget_chars": 128000,
        "cacheable": False,
        "fallback_role": None,
    },
    "consultor": {
        "llm_role": "consultor",
        "json_mode": None,
        "budget_chars": 48000,
        "cacheable": False,
        "fallback_role": "plan",  # If consultor fails, get a plan instead
    },
}

# ── Backward-compatibility aliases ────────────────────────────────────────────
_ROLE_TO_LLM: dict[str, str] = {k: v["llm_role"] for k, v in ROLE_CONFIG.items()}
_API_JSON_ROLES: set[str] = {k for k, v in ROLE_CONFIG.items() if v["json_mode"] == "api"}
_PROMPT_JSON_ROLES: set[str] = {k for k, v in ROLE_CONFIG.items() if v["json_mode"] == "prompt"}
_JSON_ROLES: set[str] = _API_JSON_ROLES | _PROMPT_JSON_ROLES
_SLEEP_LEARN_ROLES: set[str] = {
    "research", "analyze", "code", "review", "plan", "consultor"
}

# Roles with fallback chains for auto-retry on transient failure
_ROLE_FALLBACKS: dict[str, str] = {
    k: v["fallback_role"] for k, v in ROLE_CONFIG.items() if v.get("fallback_role")
}
