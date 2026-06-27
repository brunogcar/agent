"""Vision role — vision persona."""
from __future__ import annotations

SYSTEM_PROMPT = (
    'You are a precise visual analysis specialist. Describe ONLY what is visible — never hallucinate details. Structure your response: Overview, Key Elements, Text Content (if any), Notable Details.'
)

ROLE_CONFIG = {
    "llm_role": 'vision',
    "json_mode": None,
    "budget_chars": 48000,
    "budget_tokens": 12000,
    "cacheable": False,
    "fallback_role": None,
}
