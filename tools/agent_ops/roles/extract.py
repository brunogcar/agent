"""Extract role — extract persona."""
from __future__ import annotations

SYSTEM_PROMPT = (
    'You are a structured data extraction specialist. Extract the requested information exactly as it appears in the source. Output ONLY valid JSON — no prose, no markdown fences, no explanation. If a field is not found, use null. Never invent or infer values not explicitly present in the source.'
)

ROLE_CONFIG = {
    "llm_role": 'extract',
    "json_mode": 'api',
    "budget_chars": 48000,
    "budget_tokens": 12000,
    "cacheable": False,
    "fallback_role": None,
}
