"""Classify role — router persona."""
from __future__ import annotations

SYSTEM_PROMPT = (
    'You are a fast classifier. Respond with ONLY the category label — no explanation, no punctuation, no extra words. Single word or short phrase only.'
)

ROLE_CONFIG = {
    "llm_role": 'router',
    "json_mode": None,
    "budget_chars": 16000,
    "budget_tokens": 4000,
    "cacheable": True,
    "fallback_role": 'route',
}
