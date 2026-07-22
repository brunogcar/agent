"""tests/workflows/autocode/test_state_b8.py — [v3.11 B8] orphaned branch_name removal.

The vcs dict in _default_state() had a stray "branch_name": "" key that the
VCSState TypedDict no longer declared (removed in v1.4 P2). Harmless drift,
but exactly the kind of orphaned-field cleanup v3.9 was doing elsewhere.
"""
from __future__ import annotations


class TestVcsStateNoBranchName:
    """[v3.11 B8] _default_state() vcs dict must NOT have branch_name."""

    def test_vcs_dict_has_no_branch_name_key(self):
        """The vcs dict in _default_state() must not contain 'branch_name'.
        It was removed from VCSState TypedDict in v1.4 P2 but lingered in
        _default_state() until v3.11 B8."""
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="test")
        vcs = state["vcs"]
        assert "branch_name" not in vcs, (
            f"vcs dict should NOT have 'branch_name' (removed in v1.4 P2, "
            f"orphaned entry cleaned up in v3.11 B8). Got keys: {list(vcs.keys())}"
        )

    def test_vcs_dict_has_required_keys(self):
        """The vcs dict must still have the 5 keys declared in VCSState."""
        from workflows.autocode_impl.state import _default_state
        state = _default_state(task="test")
        vcs = state["vcs"]
        expected = {"commit_sha", "branch", "pushed", "pr_number", "pr_url"}
        assert set(vcs.keys()) == expected, (
            f"vcs dict keys mismatch. Expected {expected}, got {set(vcs.keys())}"
        )

    def test_get_vcs_branch_name_fallback_still_works(self):
        """commit.py has a _get_vcs(state, 'branch_name', '') fallback — it
        must still return '' even though the key no longer exists in the dict.
        _get_vcs uses .get() with a default, so this works transparently."""
        from workflows.autocode_impl.state import _get_vcs, _default_state
        state = _default_state(task="test")
        # branch_name is NOT in the dict (removed in v3.11 B8), but _get_vcs
        # returns the default "" via .get(key, default).
        result = _get_vcs(state, "branch_name", "")
        assert result == ""
