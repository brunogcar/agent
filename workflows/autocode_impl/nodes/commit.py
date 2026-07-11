"""
Git commit node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.git_ops import _git_commit
from core.tracer import tracer

def node_commit(state: AutocodeState) -> dict:
    """Commit the verified change."""
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return {}
    if not state.get("verification_passed"):
        return {"status": "skipped", "commit_sha": ""}
    # [#47] Dry-run: skip the actual commit AFTER the verification gate.
    # (The verification check above runs first so dry_run doesn't mask it.)
    if state.get("dry_run"):
        tracer.step(tid, "commit", "dry_run=True — skipping git commit")
        return {"status": "dry_run", "commit_sha": "(dry-run)"}
    plan = state.get("plan", [])
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

    result_lines = [
        f"autocode complete -- {sha or '(no new commits)'}",
        f"Branch: {state.get('branch', 'main')}",
    ]
    if state.get("skill_path"):
        result_lines.append(f"Skill: {state['skill_path']}")
    result_lines += [" ", state.get("verification_notes", " ")]
    # [Bug #10] Changed defense_note -> defense_notes (plural) to match state field
    if state.get("defense_notes"):
        result_lines.append(f"\nDefense note: {state['defense_notes']}")

    return {
        "status": "done",
        "commit_sha": sha or "",
        "result": "\n".join(result_lines)
    }