"""tests/workflows/autocode/test_git_ops_b7.py — [v3.11 B7] git_ops docstring + alias honesty.

The pre-v3.11 docstring called git_ops.py a "backward-compat wrapper" —
misleading. It's a NAME-ONLY alias; the signature changed (project_root moved
to first-positional). All in-tree callers updated; the docstring now honestly
says "name-only alias, NOT signature-compatible".
"""
from __future__ import annotations


class TestGitOpsAliasHonesty:
    """[v3.11 B7] git_ops.py aliases are name-only, not signature-compatible."""

    def test_git_commit_alias_points_at_commit(self):
        """_git_commit is the SAME function object as commit (name-only alias)."""
        from workflows.autocode_impl.git_ops import _git_commit, commit
        assert _git_commit is commit

    def test_git_create_branch_alias_points_at_create_branch(self):
        """_git_create_branch is the SAME function object as create_branch."""
        from workflows.autocode_impl.git_ops import _git_create_branch, create_branch
        assert _git_create_branch is create_branch

    def test_docstring_says_name_only_not_backward_compat(self):
        """The module docstring must NOT call itself a 'backward-compat wrapper'.
        It should say 'name-only alias' (honest about the signature change)."""
        from workflows.autocode_impl import git_ops
        docstring = git_ops.__doc__ or ""
        # The misleading "backward-compat wrapper" framing was removed in v3.11 B7.
        assert "Backward-compat wrapper" not in docstring, (
            "Module docstring should NOT say 'Backward-compat wrapper' — "
            "it's a name-only alias, not signature-compatible (v3.11 B7)."
        )
        assert "name-only" in docstring.lower() or "name only" in docstring.lower(), (
            "Module docstring should say 'name-only alias' (v3.11 B7)."
        )

    def test_docstring_mentions_breaking_signature_change(self):
        """The docstring must warn about the signature change (project_root first)."""
        from workflows.autocode_impl import git_ops
        docstring = git_ops.__doc__ or ""
        assert "BREAKING" in docstring or "signature change" in docstring.lower(), (
            "Module docstring should warn about the breaking signature change (v3.11 B7)."
        )
