
# 🧠 The Explicit Consult Tool (tools/consult.py)

## Overview
The ``consult`` tool provides a dedicated, controllable channel for the local Planner to request cloud advisory from the configured ``CONSULTOR_MODEL``. 

It is designed as an **Explicit Tool** rather than a silent system fallback. This gives the user a physical "kill switch" in the LM Studio tool registry and ensures cloud token expenditure is strictly controlled by the local orchestrator.

## Tool Signature
```python
@tool
def consult(question: str, context: str = "") -> dict:
```

## Guardrails & Safety Mechanisms
1. **The Kill Switch:** If ``CONSULTOR_MODEL`` is left blank in ``.env``, the tool instantly returns ``{"status": "disabled"}`` without making any network calls.
2. **Mechanical Context Truncation:** The ``context`` string is strictly capped at 4000 characters. If the local LLM attempts to dump a massive codebase into the context, it is silently truncated and a ``warning`` is returned in the response. We do not trust the local LLM to summarize its own state.
3. **Rate Limiting:** Backed by an in-memory sliding window in ``core/llm_backend/budget.py``. If the agent enters a loop and exceeds the RPM limit, the tool returns ``{"status": "rate_limited"}`` instead of burning API credits or getting the key banned.

## Configuration (``.env``)
The tool relies entirely on the frictionless routing defined in ``core/config.py``. 

```env
# To enable the consult tool with a cloud provider:
CONSULTOR_MODEL=openai
CONSULTOR_TIMEOUT=60

# To enable it with a local LM Studio model:
CONSULTOR_MODEL=qwen-qwen3.5-9b
CONSULTOR_TIMEOUT=60

# To completely disable the tool (Kill Switch):
CONSULTOR_MODEL=
```

## Response Schema
The tool returns a structured dictionary indicating the outcome:

- **Success:** ``{"status": "success", "provider": "openai", "model": "gpt-4o-mini", "advice": "..."}``
- **Disabled:** ``{"status": "disabled", "error": "Consultor is disabled..."}``
- **Rate Limited:** ``{"status": "rate_limited", "error": "Rate limit exceeded..."}``
- **Error:** ``{"status": "error", "provider": "...", "error": "Connection timed out..."}``

## Best Practices for the Local Planner
- **Use for High-Level Strategy:** Ask for architectural advice, debugging deadlocks, or complex logic reviews.
- **Keep Context Focused:** Do not pass entire files. Pass the specific error log, the relevant code snippet, and the exact question.
- **Do Not Use For:** Routine code generation (use the ``code`` role), simple research (use the ``web`` tool), or basic questions.

## Anti-Patterns (What to Avoid)
1. **Infinite Delegation:** Do not call ``consult`` to get an answer, fail to implement it, and call ``consult`` again with the exact same question. 
2. **Raw Context Dumping:** Do not pass 50,000 characters of raw text. The tool will mechanically truncate it at 4000 characters, and the cloud model will lose the actual question in the noise.
3. **Assuming Advice is Truth:** The tool returns the cloud model's raw advice. The local planner must still validate the suggestion (e.g., via AST checks or test runs) before executing it. The cloud model is an advisor, not the final decision-maker.