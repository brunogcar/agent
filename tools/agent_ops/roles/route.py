"""Route role — router persona."""
from __future__ import annotations

SYSTEM_PROMPT = (
    'You are a task router. Respond with ONLY a JSON object. No thinking tags. No explanation. No markdown fences. Start your response with { and end with }.\nFormat: {"workflow":"research or data or autocode or direct","tool":"web or python or file or git or memory or agent or notify or report","complexity":5,"reason":"one sentence why"}'
)

# v1.3: JSON schema for structured generation. LM Studio enforces this at
# generation time via outlines — the model cannot produce schema-invalid output.
# Matches the JSON format documented in the system prompt above.
# This is the SINGLE SOURCE OF TRUTH for the routing schema.
# core/router.py imports this constant — do not define a separate schema there.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow": {"type": "string"},
        "tool": {"type": "string"},
        "complexity": {"type": "integer"},
        "reason": {"type": "string"},
        "confidence": {"type": "string"},
        "clarifying_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["workflow", "tool", "complexity", "reason", "confidence", "clarifying_questions"],
    "additionalProperties": False,
}

ROLE_CONFIG = {
    "llm_role": 'router',
    "json_mode": 'prompt',
    "json_schema": JSON_SCHEMA,
    "budget_chars": 16000,
    "budget_tokens": 4000,
    "cacheable": True,
    "fallback_role": None,
}
