"""
Plan writing node.
"""
from __future__ import annotations
import re
from typing import Any

from workflows.autocode_helpers.state import AutocodeState, PLANNER_TIMEOUT
from workflows.autocode_helpers.constants import PLAN_SYSTEM
from workflows.autocode_helpers.helpers import _call, _parse_json_array
from core.tracer import tracer

def node_write_plan(state: AutocodeState) -> dict:
    """Generate step-by-step implementation plan."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}

    spec = state.get("spec") or state["task"]
    tracer.step(tid, "write_plan", "writing plan")

    # Phase 3/5: Inject relevant learned rules for the Planner
    from core.sleep_learn import inject_rules_into_prompt
    system = inject_rules_into_prompt(goal=spec, system_prompt=PLAN_SYSTEM, trace_id=tid)

    raw  = _call(role="planner", system=system,
                 user=f"Spec:\n{spec}", timeout=PLANNER_TIMEOUT)
    plan = _parse_json_array(raw)

    if not plan:
        plan = [
            {"id": 1, "label": "write_tests",
             "description": "Write failing tests", "acceptance": "Tests exist", "files": []},
            {"id": 2, "label": "implement",
             "description": spec[:200], "acceptance": "All tests pass", "files": []},
            {"id": 3, "label": "verify",
             "description": "Run verification", "acceptance": "All checks pass", "files": []},
        ]

    slug   = re.sub(r"[^a-z0-9]+", "-", state["task"][:40].lower()).strip("-")
    branch = f"autocode/{slug}"

    tracer.step(tid, "write_plan", f"{len(plan)} steps, branch: {branch}")
    return {"spec": spec, "plan": plan, "branch": branch, "current_step": 0}
