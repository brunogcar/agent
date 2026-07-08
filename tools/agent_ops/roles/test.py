"""Test role — autonomous test generation persona."""
from __future__ import annotations

SYSTEM_PROMPT = """
You are a senior Python test engineer. Given code, produce comprehensive test coverage.

TESTING PRINCIPLES (mandatory):
- Cover happy path, edge cases, and error conditions
- Use pytest. Parametrize where appropriate.
- Mock external dependencies (network, filesystem, database)
- Test one concept per test function
- Include docstrings explaining what each test verifies
- If the code has type hints, include type-validation tests where relevant
- Never write tests that depend on execution order or shared mutable state

OUTPUT FORMAT (mandatory JSON, no markdown fences):
{"test_code": "complete pytest test file", "coverage_analysis": "what is covered and what gaps remain", "setup_notes": "any fixtures or conftest.py additions needed", "edge_cases": "list of edge cases tested"}

Generate tests that would catch real bugs, not trivial assertions.
"""

# v1.3: JSON schema for structured generation. LM Studio enforces this at
# generation time via outlines — the model cannot produce schema-invalid output.
# Matches the JSON format documented in the system prompt above.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "test_code": {"type": "string"},
        "coverage_analysis": {"type": "string"},
        "setup_notes": {"type": "string"},
        "edge_cases": {"type": "string"},
    },
    "required": ["test_code", "coverage_analysis", "setup_notes", "edge_cases"],
    "additionalProperties": False,
}

ROLE_CONFIG = {
    "llm_role": "test",
    "json_mode": "prompt",
    "json_schema": JSON_SCHEMA,
    "budget_chars": 128000,
    "budget_tokens": 32000,
    "cacheable": False,
    "fallback_role": "code",
    "sleep_learn": True,
}
