"""Agent role configuration: LLM role mapping and JSON mode flags."""
from __future__ import annotations

# ── Role → LLM role mapping ───────────────────────────────────────────────────
# Maps agent persona → the llm.py role (which determines model + timeout).
# vision is NOT here — it delegates to tools/vision.py directly (see agent.py).

_ROLE_TO_LLM: dict[str, str] = {
    "classify": "router",   # Router — 15s
    "route": "router",      # Router — 15s
    "research": "research", # Executor — 120s
    "summarize": "summarize", # Executor — 60s
    "extract": "extract",   # Executor — 60s
    "critique": "critique", # Executor — 90s
    "analyze": "analyze",   # Executor — 90s
    "code": "code",         # Executor — 120s
    "review": "review",     # Executor — 90s
    "plan": "planner",      # Planner — 90s
    "consultor": "consultor", # Consultor — 60s

    # vision delegates to tools/vision.py — not a direct llm role
}

# Roles that use API-level json_object mode (only models that support it)
_API_JSON_ROLES = {"extract"}

# Roles that return JSON via system prompt only (parsed post-hoc)
_PROMPT_JSON_ROLES = {"route", "plan", "code", "review"}

# All roles where JSON parsing is attempted
_JSON_ROLES = _API_JSON_ROLES | _PROMPT_JSON_ROLES