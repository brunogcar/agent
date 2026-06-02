"""
core/sleep_learn/distiller.py
Active Distillation Logic.
Uses the public llm.complete() API to extract procedural rules from observations.
"""
from __future__ import annotations
import json
from typing import Dict, Any, Optional

from core.llm import llm
from core.tracer import tracer
from core.sleep_learn.filters import is_quality_rule
from core.sleep_learn.storage import save_rule

_DISTILLATION_SYSTEM_PROMPT = (
    "You are a meta-learning engine. Your job is to analyze a specific agent "
    "observation (a past error, a successful workaround, or a user correction) "
    "and distill it into a single, highly specific, actionable procedural rule.\n\n"
    "RULES FOR EXTRACTION:\n"
    "1. The rule must be technical and specific (e.g., 'When parsing JSON, always handle JSONDecodeError...').\n"
    "2. Do not output generic advice (e.g., 'Always check for errors', 'Be careful with types').\n"
    "3. Do not include dangerous operations (e.g., os.system, eval).\n"
    "4. Format your response strictly as a JSON object: {'rule': '...', 'confidence': 0.0-1.0}."
)

def distill_observation(observation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes a single observation and attempts to distill a rule.
    Returns a status dictionary.
    """
    trace_id = f"daemon_distill_{observation.get('event_type', 'unknown')}"
    obs_text = observation.get("message", "") or observation.get("content", "")
    source_id = observation.get("memory_id", "unknown")

    if not obs_text.strip():
        return {"status": "skipped", "reason": "Observation text is empty"}

    # 1. Call the public LLM API (Respects all global rate limits, budgets, and circuit breakers)
    tracer.step(trace_id, "sleep_learn", "distillation_started", observation_type=observation.get("event_type"))
    
    result = llm.complete(
        role="executor",  # Use local model to avoid cloud costs for meta-learning
        system=_DISTILLATION_SYSTEM_PROMPT,
        user=f"Analyze this observation and extract a procedural rule:\n\n{obs_text}",
        json_mode=True,
        trace_id=trace_id,
        timeout=60,
        max_tokens=256
    )

    if not result.ok:
        tracer.error(trace_id, "sleep_learn", f"LLM call failed: {result.error}")
        return {"status": "error", "reason": f"LLM call failed: {result.error}"}

    # 2. Parse and Validate the extracted rule
    parsed = result.parsed
    if not parsed or not isinstance(parsed, dict) or "rule" not in parsed:
        tracer.warning(trace_id, "sleep_learn", f"Invalid JSON schema. Raw: {result.text[:100]}")
        return {"status": "failed", "reason": "LLM did not return a valid 'rule' key in JSON"}

    rule_text = parsed["rule"]
    confidence = float(parsed.get("confidence", 0.8))

    # 3. Run through Quality & Safety Gates
    is_valid, reject_reason = is_quality_rule(rule_text)
    if not is_valid:
        tracer.step(trace_id, "sleep_learn", f"Rule rejected: {reject_reason}", rule_preview=rule_text[:50])
        return {"status": "rejected", "reason": reject_reason}

    # 4. Save to isolated storage
    rule_id = save_rule(rule_text, source_id, confidence)
    
    tracer.step(
        trace_id, "sleep_learn", "rule_saved", 
        rule_id=rule_id, confidence=confidence, rule_length=len(rule_text)
    )
    
    return {
        "status": "success", 
        "rule_id": rule_id, 
        "rule_preview": rule_text[:80] + "..." if len(rule_text) > 80 else rule_text
    }
