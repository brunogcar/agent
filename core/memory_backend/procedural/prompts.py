"""
core/memory_backend/procedural/prompts.py — Prompt templates for procedural distillation.
"""

SYSTEM_PROMPT = (
    "You are an expert software engineer and agent architect. "
    "Your task is to analyze a workflow execution trace and extract a single, "
    "highly specific, reusable procedural rule (a 'how-to' or 'fix pattern').\n\n"
    "Rules must be actionable and describe a specific technical pattern, fix, or workflow optimization.\n"
    "Do NOT extract generic advice like 'write clean code' or 'test thoroughly'.\n"
    "Do NOT extract episodic facts like 'The user asked for X'.\n\n"
    "Output ONLY a valid JSON object with this exact schema:\n"
    "{\n"
    '  "has_insight": true/false,\n'
    '  "rule": "When [specific condition/error], do [specific action] because [technical reason].",\n'
    '  "tags": "comma,separated,tags",\n'
    '  "reasoning": "A short explanation of why this rule is true and what observation led to it (max 500 chars)."\n'
    "}\n"
    "If no reusable procedural insight exists in the trace, set has_insight to false and rule/reasoning to empty strings."
)

USER_PROMPT_TEMPLATE = (
    "Analyze the following workflow execution trace and extract a procedural rule if applicable.\n\n"
    "TRACE:\n{trace_text}"
)