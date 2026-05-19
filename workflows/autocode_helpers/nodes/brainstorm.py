"""
Brainstorming node.
"""

from __future__ import annotations
from typing import Any
from workflows.autocode_helpers.state import AutocodeState, PLANNER_TIMEOUT
from workflows.autocode_helpers.constants import (
    BRAINSTORM_SYSTEM,
    AUDIT_BRAINSTORM_SYSTEM,
    FIX_BRAINSTORM_SYSTEM,
    EDIT_BRAINSTORM_SYSTEM,
    REFACTOR_BRAINSTORM_SYSTEM,
)
from workflows.autocode_helpers.helpers import _call, _parse_json, _files_context
from core.tracer import tracer

def node_brainstorm(state: AutocodeState) -> AutocodeState:
    """Refine the spec using the appropriate system prompt for the task type."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return state

    task_type = state.get("task_type", "feature")
    tracer.step(tid, "brainstorm", f"starting for {task_type}")

    # create_skill skips brainstorm entirely -- its spec is embedded in CREATE_SKILL_SYSTEM
    if task_type == "create_skill":
        tracer.step(tid, "brainstorm", "create_skill: skipping brainstorm")
        return state

    # ── Memory recall (all tasks) ──
    try:
        from core.memory import memory as _mem
        results = _mem.recall(
            query       = state["task"][:150],
            top_k       = 3,
            collections = ["procedural", "episodic"],
        )
        mem_ctx = "\n\n".join(f"[{r['type']}] {r['text']}" for r in results)
    except Exception:
        mem_ctx = ""

    files_ctx = _files_context(state["files"])

    # ── Select system prompt based on task type ──
    if task_type == "fix":
        system = FIX_BRAINSTORM_SYSTEM
    elif task_type == "edit":
        system = EDIT_BRAINSTORM_SYSTEM
    elif task_type == "refactor":
        system = REFACTOR_BRAINSTORM_SYSTEM
    elif task_type == "audit":
        system = AUDIT_BRAINSTORM_SYSTEM
    else:  # feature / unclear
        system = BRAINSTORM_SYSTEM

    user = (
        f"Task:\n{state['task']}\n\n"
        f"Relevant files:\n{files_ctx}"
        + (f"\n\nPast fixes:\n{mem_ctx}" if mem_ctx else "")
    )

    raw  = _call(role="planner", system=system, user=user, timeout=PLANNER_TIMEOUT)
    data = _parse_json(raw)

    if data.get("questions"):
        qs = "\n".join(f"- {q}" for q in data["questions"])
        return {**state, "memory_context": mem_ctx,
                "status": "needs_clarification", "result": qs}

    spec   = data.get("spec", state["task"])
    ac     = data.get("acceptance_criteria", [])
    cons   = data.get("constraints", [])
    impact = data.get("impact", [])

    if ac:
        spec += "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in ac)
    if cons:
        spec += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in cons)
    if impact:
        spec += "\n\nImpact review (files/callers to check for regressions):\n" \
                + "\n".join(f"- {i}" for i in impact)

    tracer.step(tid, "brainstorm", f"spec ready ({len(spec)} chars)")
    return {**state, "memory_context": mem_ctx, "spec": spec}