"""[v2.0] Name-only alias module — re-exports from tools.git_ops.workflow_helpers.

[v1.10 / Phase B] The local git operations (`_git_commit`, `_git_create_branch`)
were extracted to `tools/git_ops/workflow_helpers.py` (as `commit` +
`create_branch`) in Phase B of the centralize-workflow-utils refactor. This
file re-exports them under their OLD names so existing callers using
`from workflows.autocode_impl.git_ops import _git_commit` keep working.

⚠️ BREAKING — signature change (v3.11 B7 / git tool v1.3 docstring clarification):
  Old `_git_commit(message, tid="", project_root=None) -> dict`
  New `commit(project_root, message, target_file="", tid="") -> dict`

  Old `_git_create_branch(branch, tid="", project_root=None) -> bool`
  New `create_branch(project_root, branch, tid="") -> bool`

The `_git_commit` and `_git_create_branch` aliases below point at the NEW
function objects — so callers using the alias get the NEW signature
(project_root first). This is a NAME-ONLY alias, NOT a signature-compatible
backward-compat shim. All in-tree callers (commit.py, create_skill.py,
branch.py) have been updated to pass args in the new order. External callers
using the alias must also update their call site to pass project_root first.

[v3.11 B7] The pre-v3.11 docstring called this a "backward-compat wrapper" —
that was misleading (it overstates what the shim guarantees). This is a
name-only alias; the actual backward-compat handling lives in autoresearch's
`decide.py::_git_commit` wrapper which preserves the old positional order.
Autocode does NOT have such a wrapper — callers must use the new signature.
"""
from tools.git_ops.workflow_helpers import commit, create_branch

# [v3.11 B7] Name-only aliases — point at the NEW function objects (with the
# new project_root-first signature). In-tree callers have been updated to the
# new arg order. External callers using `from workflows.autocode_impl.git_ops
# import _git_commit` will get the new signature — they must update their call
# site to pass project_root first. This is NOT a signature-compatible shim.
_git_commit = commit
_git_create_branch = create_branch

__all__ = ["_git_commit", "_git_create_branch", "commit", "create_branch"]
