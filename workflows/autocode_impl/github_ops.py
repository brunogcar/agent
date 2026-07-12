"""[v2.0] Backward-compat wrapper — re-exports from vcs_ops.py.

The remote GitHub operations + swarm integration now live in vcs_ops.py
(merged with git_ops.py in Phase 5). This file re-exports them for backward
compatibility with any external callers.
"""
from workflows.autocode_impl.vcs_ops import (
    _github_is_configured,
    _github_pull,
    _github_push,
    _github_pr_create,
    _github_pr_comment,
    _github_pr_merge,
    _swarm_debug_consensus,
)

__all__ = [
    "_github_is_configured",
    "_github_pull",
    "_github_push",
    "_github_pr_create",
    "_github_pr_comment",
    "_github_pr_merge",
    "_swarm_debug_consensus",
]
