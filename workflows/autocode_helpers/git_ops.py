"""
Git helper functions for autocode workflow.
"""

from __future__ import annotations

import subprocess
from typing import Any

from core.config import cfg
from core.tracer import tracer

def _git_snapshot(message: str, tid: str = "", project_root: str = None) -> bool:
    from tools.git import git  # FIXED: Changed from tools.git_ops to tools.git
    root = project_root or str(cfg.agent_root)
    try:
        r = git(operation="snapshot", message=f"autocode: before {message[:40]}", root=root)
        ok = r.get("status") in ("committed", "nothing_to_commit")
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot @ {root}: {r.get('status')}")
        return ok
    except Exception as e:
        if tid:
            tracer.step(tid, "git_snapshot", f"snapshot failed: {e}")
        return False

def _git_commit(message: str, tid: str = "", project_root: str = None) -> str | None:
    from tools.git import git  # FIXED: Changed from tools.git_ops to tools.git
    root = project_root or str(cfg.agent_root)
    try:
        status = git(operation="status", root=root)
        if status.get("count", 0) > 0:
            r = git(operation="commit", message=message, root=root)
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
    """Create branch using snapshot pattern -- checkout not in our git tool."""
    root = project_root or str(cfg.agent_root)
    try:
        r = subprocess.run(
            ["git", "-C", root, "checkout", "-b", branch],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            # Branch exists -- switch to it
            subprocess.run(["git", "-C", root, "checkout", branch],
                           capture_output=True)
        if tid:
            tracer.step(tid, "git_branch", f"branch: {branch} @ {root}")
        return True
    except Exception as e:
        if tid:
            tracer.step(tid, "git_branch", f"branch failed: {e}")
        return False