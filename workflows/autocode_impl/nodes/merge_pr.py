"""[v2.0] Merge PR node — auto-merge the PR (DANGEROUS, default off).

Split from node_publish (Phase 3.3). This node auto-merges the PR if
AUTOCODE_AUTO_MERGE=1. Default OFF — human approval required.
"""
from __future__ import annotations

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState, _get_verify, _get_vcs  # [v2.6+v2.1] accessors
from workflows.autocode_impl.vcs_ops import _github_pr_merge


def node_merge_pr(state: AutocodeState) -> dict:
    """[v2.0] Auto-merge PR (if AUTOCODE_AUTO_MERGE=1 + PR exists).

    Returns empty dict (no state update) — merge is terminal, no downstream
    node needs the result.

    # TODO(2.0): Add AUTOCODE_AUTO_MERGE_METHOD config (squash/merge/rebase).
    """
    tid = state.get("trace_id", "")

    # Skip conditions
    if state.get("status") in ("needs_clarification", "failed", "skipped"):
        return {}
    if not _get_verify(state, "passed", False):
        return {}
    if state.get("dry_run"):
        return {}

    # If auto-merge not enabled, skip
    if not cfg.autocode_auto_merge:
        return {}

    pr_number = _get_vcs(state, "pr_number", 0)  # [v2.1] accessor
    if not pr_number:
        tracer.step(tid, "merge_pr", "no PR to merge — skipping")
        return {}

    _github_pr_merge(pr_number, tid)
    return {}
