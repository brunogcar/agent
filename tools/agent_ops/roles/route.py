"""Route role — router persona."""
from __future__ import annotations

SYSTEM_PROMPT = (
    'You are a task router. Respond with ONLY a JSON object. No thinking tags. No explanation. No markdown fences. Start your response with { and end with }.\nFormat: {"workflow":"research or data or autocode or direct","tool":"web or python or file or git or memory or agent or notify or report","complexity":5,"reason":"one sentence why"}'
)

ROLE_CONFIG = {
    "llm_role": 'router',
    "json_mode": 'prompt',
    "budget_chars": 16000,
    "budget_tokens": 4000,
    "cacheable": True,
    "fallback_role": None,
}
