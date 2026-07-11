"""
Git helper functions for autocode workflow.

[v1.3] GitHub PR integration is now implemented in github_ops.py (sibling
module). This module stays focused on LOCAL git operations (commit, branch).
The branch itself is the safety net — if something goes wrong, revert via
git. No pre-snapshot is needed since the branch isolates the changes.

See github_ops.py for:
  - _github_push(), _github_pr_create(), _github_pr_comment(), _github_pr_merge()
  - _swarm_debug_consensus()
  - _github_pull() (used by branch.py for AUTOCODE_PULL_BEFORE_BRANCH)
"""

from __future__ import annotations

import subprocess
from typing import Any

from core.config import cfg
from core.tracer import tracer


def _git_commit(message: str, tid: str = "", project_root: str = None) -> str | None:
    """Commit changes in the working tree.

    [v1.3] Push + PR creation now handled by node_publish via github_ops.py.
    This function stays focused on the local commit only.
    """
    from tools.git import git
    root = project_root or str(cfg.agent_root)
    try:
        status = git(action="status", root=root)
        if status.get("count", 0) > 0:
            r = git(action="commit", message=message, root=root)
            sha = r.get("commit_hash", "")
            if tid:
                tracer.step(tid, "git_commit", f"committed {sha} @ {root}")
            return sha
        else:
            # Nothing to commit — working tree clean
            if tid:
                tracer.step(tid, "git_commit", f"nothing to commit @ {root}")
            return None
    except Exception as e:
        if tid:
            tracer.step(tid, "git_commit", f"commit failed: {e}")
        return None


def _git_create_branch(branch: str, tid: str = "", project_root: str = None) -> bool:
    """Create branch using checkout_new action.

    Falls back to checkout_branch ONLY if checkout_new fails because the
    branch already exists. All other errors (dirty working tree, invalid
    branch name, no commits) are logged and returned as failures.

    The branch itself serves as the snapshot/safety net. No separate
    snapshot action is needed — git revert on the branch recovers state.
    """
    from tools.git import git
    root = project_root or str(cfg.agent_root)
    try:
        r = git(action="checkout_new", target=branch, root=root)
        if r.get("status") == "switched":
            if tid:
                tracer.step(tid, "git_branch", f"created and switched to {branch} @ {root}")
            return True

        # Only fall through to checkout_branch on "already exists" error
        error = r.get("error", "").lower()
        if "already exists" in error or "already a worktree" in error:
            r = git(action="checkout_branch", target=branch, root=root)
            if r.get("status") == "switched":
                if tid:
                    tracer.step(tid, "git_branch", f"switched to existing {branch} @ {root}")
                return True

        # Any other error: log and fail
        if tid:
            tracer.step(tid, "git_branch", f"failed to create {branch} @ {root}: {r.get('error', 'unknown')}")
        return False
    except Exception as e:
        if tid:
            tracer.step(tid, "git_branch", f"branch failed: {e}")
        return False
