"""[v2.0] Backward-compat wrapper — re-exports from tools.git_ops.workflow_helpers.

[v1.10 / Phase B] The local git operations (`_git_commit`, `_git_create_branch`)
were extracted to `tools/git_ops/workflow_helpers.py` (as `commit` +
`create_branch`) in Phase B of the centralize-workflow-utils refactor. This
file re-exports them under their OLD names so existing callers using
`from workflows.autocode_impl.git_ops import _git_commit` keep working.

IMPORTANT — signature change:
  Old `_git_commit(message, tid="", project_root=None) -> dict`
  New `commit(project_root, message, target_file="", tid="") -> dict`

  Old `_git_create_branch(branch, tid="", project_root=None) -> bool`
  New `create_branch(project_root, branch, tid="") -> bool`

The `_git_commit` and `_git_create_branch` aliases below point at the NEW
function objects — so callers using the alias get the NEW signature (project_root
first). All in-tree callers (commit.py, create_skill.py, branch.py) have been
updated to pass args in the new order. External callers using the alias must
also pass args in the new order.
"""
from tools.git_ops.workflow_helpers import commit, create_branch

# Backward-compat aliases — point at the NEW function objects (with the new
# project_root-first signature). In-tree callers have been updated to the new
# arg order. External callers using `from workflows.autocode_impl.git_ops
# import _git_commit` will get the new signature — they must update their call
# site to pass project_root first.
_git_commit = commit
_git_create_branch = create_branch

__all__ = ["_git_commit", "_git_create_branch", "commit", "create_branch"]
