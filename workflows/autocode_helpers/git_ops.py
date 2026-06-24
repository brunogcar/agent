"""
Git helper functions for autocode workflow.
"""

from __future__ import annotations

import subprocess
from typing import Any

from core.config import cfg
from core.tracer import tracer


def _git_snapshot(message: str, tid: str = "", project_root: str = None) -> bool:
    from tools.git import git
    root = project_root or str(cfg.agent_root)
    try:
        r = git(action="snapshot", message=f"autocode: before {message[:40]}", root=root)
        ok = r.get("status") in ("committed", "nothing_to_commit")
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot @ {root}: {r.get('status')}")
        return ok
    except Exception as e:
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot failed: {e}")
        return False


def _git_commit(message: str, tid: str = "", project_root: str = None) -> str | None:
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
            _git_snapshot(f"baseline: {message[:40]}", tid, root)
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
    """
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
