"""[v1.3] GitHub helper functions for autocode workflow.

Mirrors the git_ops.py pattern: lazy imports, project_root scoping,
tracer.step logging, structured returns.

All functions check is_configured() and graceful-skip if GitHub is not set up.
This means autocode works WITHOUT any GitHub configuration — the GitHub
integration is purely opt-in via config flags.

Integration flags (all default OFF — see core/config.py):
  - AUTOCODE_PULL_BEFORE_BRANCH: pull before creating branch
  - AUTOCODE_PUSH_ON_COMMIT: push after commit
  - AUTOCODE_OPEN_PR: create PR after push
  - AUTOCODE_AUTO_MERGE: auto-merge PR after verify (DANGEROUS)
  - AUTOCODE_DEBUG_COMMENT_PR: post root_cause as PR comment during debug
  - AUTOCODE_SWARM_DEBUG: use swarm for debug consensus

# TODO(2.0): Consider merging git_ops.py + github_ops.py into a unified
# vcs_ops.py module. They're separate in v1.3 because git (local) and
# github (remote) are separate tools with separate concerns.
"""
from __future__ import annotations

from typing import Any

from core.config import cfg
from core.tracer import tracer


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
            prompt=f"{system}\n\n{user}",
            role="executor",
        )
        if consensus_resp.get("status") != "success":
            tracer.step(tid, "swarm_debug", f"consensus failed: {consensus_resp.get('error', '')}")
            return None

        consensus_text = consensus_resp.get("data", {}).get("response", "")
        if not consensus_text:
            tracer.step(tid, "swarm_debug", "consensus returned empty response")
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
    # This gives us a confidence level (unanimous/majority/split/disagreement)
    try:
        vote_resp = swarm(
            action="vote",
            prompt=(
                f"Review this debug analysis:\n"
                f"Root cause: {root_cause[:500]}\n"
                f"Fix: {fix[:500]}\n\n"
                f"Is this root cause analysis and fix correct? Answer YES or NO."
            ),
            role="executor",
        )
        vote_data = vote_resp.get("data", {}) if vote_resp.get("status") == "success" else {}
        agreement = vote_data.get("agreement", "unknown")
        providers = vote_data.get("providers_count", 0)
    except Exception as e:
        tracer.step(tid, "swarm_debug", f"vote exception: {e}")
        agreement = "unknown"
        providers = 0

    # Map agreement to confidence level
    # TODO(2.0): Review confidence thresholds — currently:
    #   unanimous = HIGH, majority = MEDIUM, split/disagreement = LOW
    confidence_map = {
        "unanimous": "HIGH",
        "majority": "MEDIUM",
        "split": "LOW",
        "disagreement": "LOW",
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
