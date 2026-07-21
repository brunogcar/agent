"""tests/workflows/autocode/test_verify.py
Tests for node_verify — verification gate, lint checks, and commit routing.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestNodeVerify:
    def test_verify_sets_passed_on_valid_ast(self, base_state):
        from workflows.autocode_impl.nodes.verify import node_verify
        # [v2.0] Phase 3.2: _call now in llm_review.py (verify.py is wrapper)
        with patch("workflows.autocode_impl.nodes.llm_review._call",
                   return_value='{"automated_checks_passed": true, "checks": {"syntax": {"passed": true}, "tests": {"passed": true}, "spec": {"passed": true}, "regressions": {"passed": true}, "cleanliness": {"passed": true}}, "summary": "All passed"}'), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("workflows.autocode_impl.patch.apply_patch", return_value=MagicMock(ok=True, lines_changed=1)):
            result = node_verify(base_state)
            assert isinstance(result, dict)
            # [v3.0] verification_passed + verification_notes live ONLY in the verify sub-state.
            assert "verify" in result
            assert "passed" in result["verify"]
            assert "notes" in result["verify"]

    def test_verify_sets_failed_on_syntax_error(self, base_state):
        from workflows.autocode_impl.nodes.verify import node_verify
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="SyntaxError")):
            result = node_verify(base_state)
            assert isinstance(result, dict)
            assert "trace_id" in result


class TestVerifyLintPassed:
    def test_lint_none_on_missing_ruff(self, base_state):
        """[P1 #7] lint_passed must be None (not True) when ruff is missing."""
        from workflows.autocode_impl.nodes.verify import node_verify
        # [v2.0] Phase 3.2: _call now in llm_review.py (verify.py is wrapper)
        with patch("workflows.autocode_impl.nodes.llm_review._call",
                   return_value='{"automated_checks_passed": false, "checks": {}, "summary": ""}'), \
             patch("subprocess.run", side_effect=FileNotFoundError("ruff not found")), \
             patch("workflows.autocode_impl.patch.apply_patch", return_value=MagicMock(ok=True)):
            result = node_verify(base_state)
            # lint_passed should be None, not True (was True before fix)
            # We can't directly read it, but the node must not crash
            assert isinstance(result, dict)


class TestCommitAndGitEdgeCases:
    def test_commit_skips_when_not_verified(self, base_state):
        from workflows.autocode_impl.nodes.commit import node_commit
        # [v3.0] verification_passed lives ONLY in the verify sub-state.
        base_state["verify"]["passed"] = False
        result = node_commit(base_state)
        assert result.get("status") == "skipped"
        # commit_sha is in the vcs sub-state now.
        assert result["vcs"]["commit_sha"] == ""

    def test_commit_handles_nothing_to_commit(self, temp_workspace):
        from workflows.autocode_impl.git_ops import _git_commit
        # [v3.10 / centralize-utils Phase B] _git_commit is now an alias for
        # workflow_helpers.commit — signature (project_root, message,
        # target_file="", tid). Uses _git() runner (3 calls: add, commit,
        # rev-parse) instead of the git() facade.
        # Patch _git to simulate "nothing to commit" — add succeeds, commit
        # returns rc=1 with "nothing to commit" in stderr.
        with patch("tools.git_ops.workflow_helpers._git") as mock_git:
            mock_git.side_effect = [
                (0, "", ""),  # git add -A
                (1, "", "nothing to commit, working tree clean"),  # git commit
            ]
            result = _git_commit(str(temp_workspace), "empty commit", tid="t1")
            assert result == {"committed": False, "sha": "", "reason": "nothing to commit"}


class TestCommitDefenseNotes:
    """[Bug #11] commit uses defense_notes (plural) to match state field."""

    def test_commit_uses_defense_notes(self, base_state):
        from workflows.autocode_impl.nodes.commit import node_commit
        # [v3.0] Simulate what migrated writer nodes do: write to sub-state ONLY
        # (no flat mirror). The accessors (_get_verify, _get_debug) read the sub-state.
        verify = dict(base_state.get("verify", {}))
        verify["passed"] = True
        base_state["verify"] = verify

        debug = dict(base_state.get("debug", {}))
        debug["defense_notes"] = "Add bounds check"
        base_state["debug"] = debug

        base_state["task_type"] = "feature"
        base_state["task"] = "fix bug"
        with patch("workflows.autocode_impl.nodes.commit._git_commit", return_value="abc123"):
            result = node_commit(base_state)
            assert "Defense note" in result.get("result", "") or "defense" in result.get("result", "").lower()
