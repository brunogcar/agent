"""
Plan writing node.
"""
from __future__ import annotations
import re
from typing import Any
from workflows.autocode_impl.state import AutocodeState, PLANNER_TIMEOUT, _get_vcs, _get_plan  # [v3.0] _get_files removed (files is core flat)
from workflows.autocode_impl.constants import PLAN_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json_array, _blast_radius_warning  # [v1.4 P2] _blast_radius_warning extracted
from core.tracer import tracer
from core.config import cfg

def node_write_plan(state: AutocodeState) -> dict:
    """Generate step-by-step implementation plan."""
    tid = state.get("trace_id", "")
    if state.get("status") == "needs_clarification":
        return {}
    
    spec = _get_plan(state, "spec", "") or state["task"]  # [v2.2] accessor
    tracer.step(tid, "write_plan", "writing plan")

    # Phase 3/5: Inject relevant learned rules for the Planner
    from core.sleep_learn import inject_rules_into_prompt
    system = inject_rules_into_prompt(goal=spec, system_prompt=PLAN_SYSTEM, trace_id=tid)

    # ── Phase 8: Blast Radius Context Injection for Planner ──
    # [v1.4 P2] Inline block extracted to helpers._blast_radius_warning().
    project_root = state.get("project_root", "")
    files_in_context = list(state.get("files", {}).keys())  # [v3.0] files is core flat field
    blast_radius_note = _blast_radius_warning(project_root, files_in_context, tid)

    raw  = _call(role="planner", system=system,
                 user=f"Spec:\n{spec}{blast_radius_note}", timeout=PLANNER_TIMEOUT, trace_id=tid)  # [v1.2 P1] attribute retry-exhaustion errors
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
    # [P1 #12] If task is all non-alphanumeric (e.g., Chinese text), slug is empty.
    # Fallback to "autocode" to prevent invalid branch name "autocode/".
    if not slug:
        slug = "autocode"
    # [Pre-2.0 Fix] Append trace_id suffix for uniqueness across runs.
    # Was: two runs with same task → same branch → second run checks out first
    # run's branch → cross-contamination / git history corruption.
    # TODO(2.0): Consider making this configurable (some users may want reusable branches).
    tid_suffix = tid.replace("-", "")[:8] if tid else "notrace"
    branch = f"autocode/{slug}-{tid_suffix}"

    tracer.step(tid, "write_plan", f"{len(plan)} steps, branch: {branch}")
    # [v2.1] RMW: write to vcs sub-state for branch
    current_vcs = dict(state.get("vcs", {}))
    current_vcs["branch"] = branch
    # [v2.2] RMW: write to plan sub-state for spec, plan, current_step
    current_plan = dict(state.get("plan_state", {}))
    current_plan["spec"] = spec
    current_plan["plan"] = plan
    current_plan["current_step"] = 0
    return {"vcs": current_vcs, "plan_state": current_plan}
