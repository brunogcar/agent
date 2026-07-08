# core/memory_backend/procedural/distill.py — LLM lesson extraction pipeline.
"""Synchronous distillation pipeline."""
from __future__ import annotations

import json

from core.tracer import tracer
from core.memory_engine import memory # Import the facade to store the result
from core.memory_backend.procedural.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from core.memory_backend.procedural.validate import is_valid_rule

def distill_workflow(trace_text: str, trace_id: str, timeout: int = 15) -> dict:
    """
    Synchronous distillation pipeline.
    Calls the Planner LLM, parses JSON, validates, and stores as procedural memory.

    Relies on the httpx timeout inside core/llm.py to sever the socket and
    abort LM Studio generation, preventing VRAM "Ghost Thread" leaks.
    """
    from core.llm import llm # Lazy import to avoid circular deps

    if not trace_text or len(trace_text.strip()) < 50:
        return {"status": "skipped", "reason": "trace_too_short"}

    # Truncate trace to prevent VRAM explode on local models
    if len(trace_text) > 5000:
        trace_text = trace_text[:2000] + "\n...[TRUNCATED]...\n" + trace_text[-2000:]

    user_prompt = USER_PROMPT_TEMPLATE.format(trace_text=trace_text)

    try:
        # Memory v1.2: JSON schema enforcement — LM Studio enforces the distillation
        # schema at generation time. The model cannot produce has_insight/
        # rule/tags with wrong types or missing fields.
        _DISTILL_JSON_SCHEMA = {
            "type": "object",
            "properties": {
                "has_insight": {"type": "boolean"},
                "rule": {"type": "string"},
                "tags": {"type": "string"},
            },
            "required": ["has_insight", "rule", "tags"],
            "additionalProperties": False,
        }
        # The timeout parameter is passed directly to llm.complete(), which passes it
        # to httpx.Client.post(). If it hits 15s, httpx severs the socket,
        # instantly freeing LM Studio's VRAM. No ThreadPoolExecutor needed.
        result = llm.complete(
            role="planner",
            system=SYSTEM_PROMPT,
            user=user_prompt,
            content="",
            trace_id=trace_id,
            temperature=0.2,
            timeout=timeout,
            json_schema=_DISTILL_JSON_SCHEMA,
        )
    except Exception as e:
        tracer.error(trace_id, "distill", f"LLM call failed: {e}")
        return {"status": "skipped", "reason": "llm_error"}

    if not result.ok:
        return {"status": "skipped", "reason": "llm_not_ok", "error": result.error}

    # Parse JSON
    raw_text = result.text.strip()
    # Strip markdown code blocks if the LLM wrapped it
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        tracer.warning(trace_id, "distill", f"Failed to parse JSON: {raw_text[:100]}")
        return {"status": "skipped", "reason": "invalid_json"}

    if not data.get("has_insight"):
        return {"status": "skipped", "reason": "no_insight"}

    rule_text = data.get("rule", "")
    tags = data.get("tags", "procedural,auto")

    # Validate
    is_valid, reason = is_valid_rule(rule_text)
    if not is_valid:
        tracer.step(trace_id, "distill", f"Rule rejected: {reason}")
        return {"status": "skipped", "reason": f"validation_failed_{reason}"}

    # Store
    store_result = memory.store_procedural(
        text=rule_text,
        importance=8,
        tags=tags,
        trace_id=trace_id,
        goal="workflow_distillation",
        outcome="success"
    )

    return {"status": "stored", "rule_preview": rule_text[:80], "store_result": store_result}
