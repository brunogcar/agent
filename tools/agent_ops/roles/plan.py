"""Plan role — planner persona."""
from __future__ import annotations

SYSTEM_PROMPT = """
You are a task planning specialist for an autonomous AI agent. Break the given goal into a clear, ordered sequence of steps. Each step must be concrete and executable by the agent's available tools: web, python, file, git, memory, notify, report, agent, vision.

OUTPUT: valid JSON only. No thinking tags. No markdown fences. Start with { and end with }.
Format: {"goal":"restated goal","steps":[{"step":1,"action":"tool_name","description":"what to do","inputs":{"key":"value"}}],"estimated_complexity":5,"risks":["failure point 1"]}
"""

# v1.3: JSON schema for structured generation. LM Studio enforces this at
# generation time via outlines — the model cannot produce schema-invalid output.
# Matches the JSON format documented in the system prompt above.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer"},
                    "action": {"type": "string"},
                    "description": {"type": "string"},
                    "inputs": {"type": "object", "additionalProperties": True},
                },
                "required": ["step", "action", "description", "inputs"],
            },
        },
        "estimated_complexity": {"type": "integer"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "steps", "estimated_complexity", "risks"],
    "additionalProperties": False,
}

ROLE_CONFIG = {
    "llm_role": "planner",
    "json_mode": "prompt",
    "json_schema": JSON_SCHEMA,
    "budget_chars": 128000,
    "budget_tokens": 32000,
    "cacheable": False,
    "fallback_role": None,
    "sleep_learn": True,
}
