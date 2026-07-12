"""[v2.0] Backward-compat wrapper — re-exports from vcs_ops.py.

The local git operations (_git_commit, _git_create_branch) now live in
vcs_ops.py (merged with github_ops.py in Phase 5). This file re-exports
them for backward compatibility with any external callers.
"""
from workflows.autocode_impl.vcs_ops import _git_commit, _git_create_branch

__all__ = ["_git_commit", "_git_create_branch"]
