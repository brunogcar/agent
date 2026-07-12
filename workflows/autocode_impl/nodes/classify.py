"""
Task classification node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState, ROUTER_TIMEOUT
from workflows.autocode_impl.constants import TASK_CLASSIFIER_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from core.tracer import tracer

# [Hardening P1.6] JSON schema for the classify LLM call.
# LM Studio enforces this at generation time via outlines, so the model cannot
# emit a missing/invalid task_type. Enum matches the values the rest of the
# pipeline (classify override, routes, brainstorm system-prompt selector) expects.
_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "task_type": {
            "type": "string",
            "enum": ["feature", "audit", "edit", "fix", "refactor", "create_skill", "unclear"],
        },
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["task_type"],
    "additionalProperties": False,
}

def node_classify_task(state: AutocodeState) -> dict:
    """Classify task type to route feature vs fix/refactor/edit/create_skill paths."""
    tid = state.get("trace_id", "")
    tracer.step(tid, "classify_task", f"classifying: {state['task'][:60]}")
    raw  = _call(
        role    = "router",
        system  = TASK_CLASSIFIER_SYSTEM,
        user    = f"Task:\n{state['task']}",
        timeout = ROUTER_TIMEOUT,
        json_schema=_CLASSIFY_SCHEMA,  # [Hardening P1.6]
    )
    data      = _parse_json(raw)
    task_type = data.get("task_type", "feature")
    questions = data.get("questions", [])

    # Mode override takes priority over Router classification.
    mode = state.get("mode", "")
    if mode == "fix_error":
        task_type = "fix"
    elif mode == "improve":
        task_type = "refactor"
    elif mode == "edit":
        task_type = "edit"
    elif mode == "create_skill":
        task_type = "create_skill"
    elif mode == "audit":
        task_type = "audit"

    tracer.step(tid, "classify_task", f"classified as: {task_type}")

    if questions and task_type == "unclear":
        qs = "\n".join(f"- {q}" for q in questions)
        return {
            "task_type": task_type,
            "status": "needs_clarification",
            "result": qs
        }

    return {"task_type": task_type}