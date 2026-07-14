"""
Git commit node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_impl.state import AutocodeState  # [v2.0.5] _get_vcs removed (split-brain — see P1-1)
from workflows.autocode_impl.vcs_ops import _git_commit
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

    # [v2.0.5] P1-1: Was `_get_vcs(state, 'branch', 'main')` — broken split-brain.
    # _get_vcs reads state["vcs"]["branch"] first, which holds the stale default
    # "" (sub-state populated by _default_state() but never written to by nodes —
    # node_write_plan writes the flat "branch" field). The accessor returned ""
    # instead of the actual branch name. Read flat fields directly until the
    # sub-state migration is complete (roadmap: v2.x → v3.0). NEVER DO #33 updated.
    branch_for_msg = state.get("branch") or state.get("branch_name") or "main"
    result_lines = [
        f"autocode complete -- {sha or '(no new commits)'}",
        f"Branch: {branch_for_msg}",
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