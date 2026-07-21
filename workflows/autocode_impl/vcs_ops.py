"""[v2.0] Unified VCS helper functions for autocode workflow.

[v1.10 / Phase B] Local git operations (`_git_commit`, `_git_create_branch`)
have been EXTRACTED to `tools/git_ops/workflow_helpers.py` (commit,
create_branch, reset_hard). This module now ONLY contains:
  - Remote operations (was github_ops.py): _github_pull, _github_push,
    _github_pr_create, _github_pr_comment, _github_pr_merge
  - Swarm integration (was github_ops.py): _swarm_debug_consensus

The backward-compat shim `workflows/autocode_impl/git_ops.py` re-exports
`_git_commit` + `_git_create_branch` from `tools.git_ops.workflow_helpers`
(aliased to the new function names) so external callers using the old
import path keep working.

All functions follow the same pattern: lazy imports, project_root scoping,
tracer.step logging, structured returns.

Section layout:
  === Remote operations (was github_ops.py) ===
    _github_pull(), _github_push(), _github_pr_create(),
    _github_pr_comment(), _github_pr_merge()
  === Swarm integration (was github_ops.py) ===
    _swarm_debug_consensus()

[v1.2] Removed unused `from typing import Any` import.
"""
from __future__ import annotations

from core.config import cfg
from core.tracer import tracer


# === Local operations (was git_ops.py) ===
# [v1.10 / Phase B] _git_commit + _git_create_branch DELETED — moved to
# tools/git_ops/workflow_helpers.py. Backward-compat aliases live in
# workflows/autocode_impl/git_ops.py.


# === Remote operations (was github_ops.py) ===

def _github_is_configured() -> bool:
    """Check if GitHub is configured (token + owner + repo all set).

    Wrapper around tools.github_ops.client.is_configured() with a
    try/except so autocode never crashes if the github tool isn't
    importable for some reason.
    """
    try:
        from tools.github_ops.client import is_configured
        return is_configured()
    except Exception:
        return False


def _github_pull(tid: str = "") -> bool:
    """Pull recent commits from remote via github(action="pull").

    Returns True on success, False on failure or if not configured.
    Does NOT require a branch param — pulls the current branch.
    """
    if not _github_is_configured():
        tracer.step(tid, "github_pull", "skipped — GitHub not configured")
        return False
    from tools.github import github
    try:
        r = github(action="pull", remote="origin")
        if r.get("status") == "success":
            tracer.step(tid, "github_pull", "pulled from origin")
            return True
        tracer.step(tid, "github_pull", f"failed: {r.get('error', 'unknown')}")
        return False
    except Exception as e:
        tracer.step(tid, "github_pull", f"exception: {e}")
        return False


def _github_push(branch: str, tid: str = "") -> bool:
    """Push a branch to the remote via github(action="push").

    Returns True on success, False on failure or if not configured.
    """
    if not _github_is_configured():
        tracer.step(tid, "github_push", "skipped — GitHub not configured")
        return False
    if not branch:
        tracer.step(tid, "github_push", "skipped — no branch name")
        return False
    from tools.github import github
    try:
        r = github(action="push", branch=branch, remote="origin", force=False)
        if r.get("status") == "success":
            tracer.step(tid, "github_push", f"pushed {branch} to origin")
            return True
        tracer.step(tid, "github_push", f"failed: {r.get('error', 'unknown')}")
        return False
    except Exception as e:
        tracer.step(tid, "github_push", f"exception: {e}")
        return False


def _github_pr_create(branch: str, title: str, body: str, tid: str = "") -> dict | None:
    """Create a PR from a branch via github(action="pr_create").

    Returns PR data dict {number, title, url, state} on success, None on failure.
    """
    if not _github_is_configured():
        tracer.step(tid, "github_pr_create", "skipped — GitHub not configured")
        return None
    if not branch:
        tracer.step(tid, "github_pr_create", "skipped — no branch name")
        return None
    from tools.github import github
    try:
        r = github(action="pr_create", title=title, head=branch, base="main", body=body)
        if r.get("status") == "success":
            data = r.get("data", {})
            tracer.step(tid, "github_pr_create", f"PR #{data.get('number')} created")
            return data
        tracer.step(tid, "github_pr_create", f"failed: {r.get('error', 'unknown')}")
        return None
    except Exception as e:
        tracer.step(tid, "github_pr_create", f"exception: {e}")
        return None


def _github_pr_comment(number: int, body: str, tid: str = "") -> bool:
    """Post a comment on a PR via github(action="pr_comment").

    Returns True on success, False on failure.
    """
    if not _github_is_configured():
        return False
    if not number:
        return False
    from tools.github import github
    try:
        r = github(action="pr_comment", number=number, body=body)
        if r.get("status") == "success":
            tracer.step(tid, "github_pr_comment", f"commented on PR #{number}")
            return True
        return False
    except Exception as e:
        tracer.step(tid, "github_pr_comment", f"exception: {e}")
        return False


def _github_pr_merge(number: int, tid: str = "") -> bool:
    """Merge a PR via github(action="pr_merge").

    Returns True on success, False on failure.
    # TODO(2.0): Add merge_method config option (squash/merge/rebase).
    """
    if not _github_is_configured():
        return False
    if not number:
        return False
    from tools.github import github
    try:
        r = github(action="pr_merge", number=number, merge_method="squash")
        if r.get("status") == "success":
            tracer.step(tid, "github_pr_merge", f"merged PR #{number}")
            return True
        tracer.step(tid, "github_pr_merge", f"failed: {r.get('error', 'unknown')}")
        return False
    except Exception as e:
        tracer.step(tid, "github_pr_merge", f"exception: {e}")
        return False


# === Swarm integration (was github_ops.py) ===

def _swarm_debug_consensus(system: str, user: str, tid: str = "") -> dict | None:
    """Get swarm consensus on a debug fix.

    2-run pattern:
      Run 1: swarm(action="consensus") — all providers propose a fix
      Run 2: swarm(action="vote") — providers vote on the consensus fix

    Returns dict with:
      {fix: str, root_cause: str, defense_notes: str,
       confidence: "HIGH"|"MEDIUM"|"LOW", agreement: str, providers: int}

    Returns None if swarm is not available (no providers configured).
    Non-blocking: failures return None, caller falls back to single-LLM debug.

    v1.0.2 (swarm): Fixed 7 interface bugs that made this function completely
    non-functional (found by cross-LLM review — DeepSeek + MiMo independently):
      - `prompt=` → `question=` (swarm facade param is `question`, not `prompt`)
      - `role="executor"` dropped (not a swarm param — silently absorbed by **kwargs)
      - `.get("response")` → `.get("synthesis")` (consensus returns `synthesis`)
      - `providers_count` → `provider_count` (field name in swarm result)
      - Added `single_response` to confidence_map (swarm v1.0.1 addition → LOW)
      - Pass `trace_id=tid` so swarm calls are traced
      - Check `synthesis_failed` flag (swarm v1.0.2 addition) and bail if synthesis
        failed rather than parsing an empty string
    """
    try:
        from tools.swarm import swarm
    except Exception as e:
        tracer.step(tid, "swarm_debug", f"swarm not importable: {e}")
        return None

    # Run 1: consensus — all providers propose
    try:
        consensus_resp = swarm(
            action="consensus",
            question=f"{system}\n\n{user}",
            trace_id=tid,
        )
        if consensus_resp.get("status") != "success":
            tracer.step(tid, "swarm_debug", f"consensus failed: {consensus_resp.get('error', '')}")
            return None

        consensus_data = consensus_resp.get("data", {})
        # v1.0.2: Check synthesis_failed flag (swarm v1.0.2 addition). If the
        # planner synthesis crashed, consensus_text is empty — bail rather than
        # parse nothing.
        if consensus_data.get("synthesis_failed"):
            tracer.step(tid, "swarm_debug", f"consensus synthesis failed: {consensus_data.get('synthesis_error', '')}")
            return None

        consensus_text = consensus_data.get("synthesis", "")
        if not consensus_text:
            tracer.step(tid, "swarm_debug", "consensus returned empty synthesis")
            return None
    except Exception as e:
        tracer.step(tid, "swarm_debug", f"consensus exception: {e}")
        return None

    # Parse the consensus response as JSON (it should be {root_cause, defense_notes, fix})
    import json
    from workflows.autocode_impl.helpers import _parse_json
    try:
        debug_data = json.loads(consensus_text.strip())
    except json.JSONDecodeError:
        debug_data = _parse_json(consensus_text)
        if not debug_data:
            debug_data = {"root_cause": "Unknown", "defense_notes": "", "fix": consensus_text[:2000]}

    root_cause = debug_data.get("root_cause", "Unknown")
    fix = debug_data.get("fix", "")
    defense_notes = debug_data.get("defense_notes", "")

    # Run 2: vote — providers vote on whether the root_cause + fix is correct
    # This gives us a confidence level (unanimous/majority/split/disagreement/single_response)
    try:
        vote_resp = swarm(
            action="vote",
            question=(
                f"Review this debug analysis:\n"
                f"Root cause: {root_cause[:500]}\n"
                f"Fix: {fix[:500]}\n\n"
                f"Is this root cause analysis and fix correct? Answer YES or NO."
            ),
            trace_id=tid,
        )
        vote_data = vote_resp.get("data", {}) if vote_resp.get("status") == "success" else {}
        agreement = vote_data.get("agreement", "unknown")
        providers = vote_data.get("provider_count", 0)
    except Exception as e:
        tracer.step(tid, "swarm_debug", f"vote exception: {e}")
        agreement = "unknown"
        providers = 0

    # Map agreement to confidence level
    # v1.0.2: Added single_response → LOW (swarm v1.0.1 addition). A single
    # voter cannot express agreement; treating it as HIGH (the old behavior
    # when single_response was misclassified as unanimous) was wrong.
    # TODO(2.0): Review confidence thresholds — currently:
    #   unanimous = HIGH, majority = MEDIUM, split/disagreement/single_response = LOW
    confidence_map = {
        "unanimous": "HIGH",
        "majority": "MEDIUM",
        "split": "LOW",
        "disagreement": "LOW",
        "single_response": "LOW",
    }
    confidence = confidence_map.get(agreement, "LOW")

    tracer.step(tid, "swarm_debug", f"confidence={confidence}, agreement={agreement}, providers={providers}")

    return {
        "fix": fix,
        "root_cause": root_cause,
        "defense_notes": defense_notes,
        "confidence": confidence,
        "agreement": agreement,
        "providers": providers,
    }
