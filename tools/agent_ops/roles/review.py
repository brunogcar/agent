"""Review role — review persona."""
from __future__ import annotations

SYSTEM_PROMPT = """
You are a senior Python code reviewer. Review the provided patch or code change.

CHECK FOR (in this order):
1. Correctness — does it actually solve the stated problem?
2. Bugs — new errors introduced, off-by-one, uncaught exceptions
3. Edge cases — empty input, None values, large data, concurrent access
4. Breaking changes — function signature changes, import changes
5. Style — PEP 8, type hints, docstrings
6. Performance — unnecessary loops, blocking calls, memory leaks

OUTPUT FORMAT (mandatory JSON, no markdown fences):
{"verdict": "APPROVE|REVISE|REJECT", "issues": [{"severity": "critical|warning|info", "description": "...", "fix": "..."}], "corrected_patch": "corrected code if verdict is REVISE, else null"}
"""

# v1.3: JSON schema for structured generation. LM Studio enforces this at
# generation time via outlines — the model cannot produce schema-invalid output.
# Matches the JSON format documented in the system prompt above.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["APPROVE", "REVISE", "REJECT"]},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                    "description": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["severity", "description", "fix"],
            },
        },
        # Hardening fix: Changed from ["string", "null"] to "string" with default "".
        # Small local models may produce the string "null" instead of JSON null,
        # which would be stored as the string "null" — confusing downstream consumers.
        # Empty string is safer and handled correctly by all consumers. The system
        # prompt says "else null" — update to "else empty string" for consistency.
        "corrected_patch": {"type": "string", "default": ""},
    },
    "required": ["verdict", "issues", "corrected_patch"],
    "additionalProperties": False,
}

ROLE_CONFIG = {
    "llm_role": "review",
    "json_mode": "prompt",
    "json_schema": JSON_SCHEMA,
    "budget_chars": 48000,
    "budget_tokens": 12000,
    "cacheable": False,
    "fallback_role": None,
    "sleep_learn": True,
}
