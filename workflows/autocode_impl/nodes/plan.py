"""
Plan writing node.
"""
from __future__ import annotations
import re
from typing import Any
from workflows.autocode_impl.state import AutocodeState, PLANNER_TIMEOUT
from workflows.autocode_impl.constants import PLAN_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json_array
from core.tracer import tracer
from core.config import cfg
from core.kgraph.queries import get_callers

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

    # ── Phase 8: Blast Radius Context Injection for Planner ──
    blast_radius_note = ""
    project_root = state.get("project_root", "")
    files_in_context = list(state.get("files", {}).keys())

    if project_root and files_in_context:
        try:
            from pathlib import Path
            from core.kgraph.project import is_same_path, ProjectManager
            
            is_agent = is_same_path(Path(project_root), cfg.agent_root)
            pm = ProjectManager(project_path=project_root, is_agent_root=is_agent)
             
            callers = []
            # Limit to top 3 files to prevent excessive DB queries
            for f in files_in_context[:3]:
                deps = get_callers(pm.path, f)
                callers.extend([c for c in deps if c not in files_in_context])
            
            if callers:
                # 🔴 Limit to top 5 unique callers to prevent token overflow (Mistral's recommendation)
                unique_callers = list(set(callers))[:5]
                blast_radius_note = f"\n\n⚠️ BLAST RADIUS WARNING: The files you are planning to modify are also used by: {', '.join(unique_callers)}. Ensure your plan includes steps to verify these callers are not broken."
        except Exception as e:
            # 🔴 Phase 8 Final Polish: Observability for KG query failures
            tracer.warning(tid, "write_plan", f"Blast radius query failed: {e}")

    raw  = _call(role="planner", system=system,
                 user=f"Spec:\n{spec}{blast_radius_note}", timeout=PLANNER_TIMEOUT)
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
    return {"spec": spec, "plan": plan, "branch": branch, "current_step": 0}