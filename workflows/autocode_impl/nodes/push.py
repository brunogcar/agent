"""[v2.0] Push node — push branch to remote.

Split from node_publish (Phase 3.3). This node pushes the branch to the
remote via github(action="push"). PR creation and auto-merge are handled
by separate nodes:
  - node_create_pr (next)
  - node_merge_pr (after create_pr)
"""
from __future__ import annotations

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState, _get_verify  # [v2.6] accessor
from workflows.autocode_impl.vcs_ops import _github_push


def node_push(state: AutocodeState) -> dict:
    """[v2.0] Push branch to remote (if AUTOCODE_PUSH_ON_COMMIT=1).

    Returns partial state update with:
      - pushed: bool (True if push succeeded)
    """
    tid = state.get("trace_id", "")

    # Skip conditions — same as node_commit
    if state.get("status") in ("needs_clarification", "failed", "skipped"):
        return {}
    if not _get_verify(state, "passed", False):
        return {}
    if state.get("dry_run"):
        tracer.step(tid, "push", "dry_run=True — skipping push")
        return {"status": "dry_run"}

    # If push not enabled, skip (but let downstream nodes decide)
    if not cfg.autocode_push_on_commit:
        return {"pushed": False}

    branch = state.get("branch", "")
    if not branch:
        tracer.step(tid, "push", "no branch in state — skipping")
        return {"pushed": False}

    success = _github_push(branch, tid)
    return {"pushed": success}
