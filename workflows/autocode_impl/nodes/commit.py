"""
Git commit node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState, _get_debug, _get_verify, _get_vcs, _get_plan  # [v2.5+v2.6+v2.1+v2.2] accessors
from workflows.autocode_impl.vcs_ops import _git_commit
from core.tracer import tracer

def node_commit(state: AutocodeState) -> dict:
    """Commit the verified change."""
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return {}
    if not _get_verify(state, "passed", False):
        # [v2.1] RMW: write to vcs sub-state + flat mirror
        current_vcs = dict(state.get("vcs", {}))
        current_vcs["commit_sha"] = ""
        return {"status": "skipped", "commit_sha": "", "vcs": current_vcs}
    # [#47] Dry-run: skip the actual commit AFTER the verification gate.
    # (The verification check above runs first so dry_run doesn't mask it.)
    if state.get("dry_run"):
        tracer.step(tid, "commit", "dry_run=True — skipping git commit")
        # [v2.1] RMW: write to vcs sub-state + flat mirror
        current_vcs = dict(state.get("vcs", {}))
        current_vcs["commit_sha"] = "(dry-run)"
        return {"status": "dry_run", "commit_sha": "(dry-run)", "vcs": current_vcs}
    plan = _get_plan(state, "plan", [])  # [v2.2] accessor
    # [Pre-2.0 Fix] Was: s["label"] — KeyError if any step lacks "label".
    # Now uses .get("label", "step") fallback.
    labels = ", ".join(
        s.get("label", "step") for s in plan
        if s.get("label", "step") not in ("write_tests", "verify")
    )
    task_type = state.get("task_type", "feature")
    msg = (
        f"{'skill' if task_type == 'create_skill' else 'feat'}(autocode): "
        f"{state['task'][:60]}\n\n"
        f"- Type: {task_type}\n"
        + (f"- Steps: {labels}\n" if labels else "")
        + (f"- Skill: {state.get('skill_path', '')}\n" if state.get("skill_path") else "")
        + f"- Tests: pass\n"
        f"- Verified: yes"
    )

    # [GIT SCOPING] Route commit to workspace project if set, else agent_root
    root = state.get("project_root")
    sha = _git_commit(msg, tid, root)
    tracer.step(tid, "commit", f"sha: {sha} @ {root or 'agent_root'}")

    # [v2.1] Use _get_vcs accessor (was v2.0.5 band-aid: state.get("branch") directly).
    # Now that plan.py writes to the vcs sub-state via RMW, the accessor is safe.
    branch_for_msg = _get_vcs(state, "branch", "") or _get_vcs(state, "branch_name", "") or "main"
    result_lines = [
        f"autocode complete -- {sha or '(no new commits)'}",
        f"Branch: {branch_for_msg}",
    ]
    if state.get("skill_path"):
        result_lines.append(f"Skill: {state['skill_path']}")
    result_lines += [" ", _get_verify(state, "notes", " ")]
    # [Bug #10] Changed defense_note -> defense_notes (plural) to match state field
    # [v2.5] Use _get_debug accessor (reads sub-state first, falls back to flat)
    defense_notes = _get_debug(state, "defense_notes", "")
    if defense_notes:
        result_lines.append(f"\nDefense note: {defense_notes}")

    # [v2.1] RMW: write to vcs sub-state + flat mirror
    current_vcs = dict(state.get("vcs", {}))
    current_vcs["commit_sha"] = sha or ""
    return {
        "status": "done",
        "commit_sha": sha or "",
        "result": "\n".join(result_lines),
        "vcs": current_vcs,
    }