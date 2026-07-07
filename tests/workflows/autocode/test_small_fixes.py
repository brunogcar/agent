"""tests/workflows/autocode/test_small_fixes.py
Tests for the v1.1.2 small-fix batch: #39 (stuck detection), #44 (structured
artifacts), #46 (multi-file git-diff), #47 (dry-run guards).

All tests use tmp_path + mocks — nothing touches the real project.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


# ─── #39: Stuck detection in debug loop ────────────────────────────────────

class TestStuckDetection:
    """[#39] Same error signature on consecutive iterations → bail to verify."""

    def test_error_signature_extracts_last_3_lines(self):
        from workflows.autocode_impl.nodes.run_tests import _error_signature
        err = "line1\nline2\nline3\nline4\nline5"
        sig = _error_signature(err)
        assert sig == "line3\nline4\nline5"

    def test_error_signature_empty(self):
        from workflows.autocode_impl.nodes.run_tests import _error_signature
        assert _error_signature("") == ""
        assert _error_signature("   ") == ""

    def test_stuck_sets_tdd_status_stuck(self, mocker):
        """When the same error repeats on iteration >1, tdd_status='stuck'."""
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        # Mock run_tests_on_disk to return the same stderr as last iteration
        same_error = "AssertionError: expected 5 got 3\n  assert x == 5\n  where x = 3"
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": same_error, "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"],
            "tdd_iteration": 1,  # will become 2 (>1 triggers stuck check)
            "last_test_error": same_error,  # same error as this iteration
            "trace_id": "t1",
        }
        # Patch the file-existence check
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "stuck", (
            f"Same error on iteration 2 must set tdd_status='stuck'; got {result['tdd_status']!r}"
        )
        assert result["last_test_error"] == same_error

    def test_different_error_does_not_trigger_stuck(self, mocker):
        """Different error on consecutive iterations → tdd_status='failed' (not stuck)."""
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": "NEW error this time", "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"],
            "tdd_iteration": 1,
            "last_test_error": "OLD different error",
            "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "failed", (
            "Different errors must not trigger stuck — should be 'failed'"
        )

    def test_first_failure_does_not_trigger_stuck(self, mocker):
        """First iteration failure (no prev_error) → tdd_status='failed'."""
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": False, "stderr": "some error", "stdout": ""},
        )
        state = {
            "test_files": ["test_x.py"],
            "tdd_iteration": 0,  # first iteration
            "last_test_error": "",  # no previous error
            "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "failed"

    def test_success_clears_last_test_error(self, mocker):
        """Passing tests must clear last_test_error so a later failure isn't 'stuck'."""
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        mocker.patch(
            "workflows.autocode_impl.nodes.run_tests.run_tests_on_disk",
            return_value={"success": True, "stderr": "", "stdout": "1 passed"},
        )
        mocker.patch("core.memory_engine.memory.store")
        state = {
            "test_files": ["test_x.py"],
            "tdd_iteration": 2,
            "last_test_error": "old error",
            "trace_id": "t1",
        }
        mocker.patch("pathlib.Path.exists", return_value=True)
        result = node_run_tests(state)
        assert result["tdd_status"] == "passed"
        assert result["last_test_error"] == "", "Success must clear last_test_error"

    def test_route_stuck_goes_to_verify(self):
        """[#39] route_after_run_tests must send 'stuck' to node_verify."""
        from workflows.autocode_impl.routes import route_after_run_tests
        assert route_after_run_tests({"tdd_status": "stuck"}) == "node_verify"


# ─── #44: Structured artifacts ─────────────────────────────────────────────

class TestStructuredArtifacts:
    """[#44] run_autocode_agent must return a typed artifacts dict."""

    def test_shape_artifacts_extracts_fields(self):
        from workflows.autocode import _shape_artifacts
        final_state = {
            "commit_sha": "abc123",
            "branch_name": "fix-bug",
            "modified_files": ["a.py", "b.py"],
            "test_results": {"success": True, "stdout": "1 passed"},
            "tdd_status": "passed",
            "tdd_iteration": 2,
            "verification_passed": True,
            "skill_created": False,
            "skill_path": "",
        }
        art = _shape_artifacts(final_state)
        assert art["commit_sha"] == "abc123"
        assert art["branch_name"] == "fix-bug"
        assert art["modified_files"] == ["a.py", "b.py"]
        assert art["test_results"]["success"] is True
        assert art["tdd_status"] == "passed"
        assert art["tdd_iteration"] == 2
        assert art["verification_passed"] is True
        assert art["skill_created"] is False

    def test_shape_artifacts_defaults_on_empty_state(self):
        from workflows.autocode import _shape_artifacts
        art = _shape_artifacts({})
        assert art["commit_sha"] == ""
        assert art["modified_files"] == []
        assert art["tdd_iteration"] == 0
        assert art["verification_passed"] is False

    def test_run_autocode_agent_attaches_artifacts(self):
        """[#44] The return dict must include an 'artifacts' key."""
        from workflows.autocode import run_autocode_agent
        with patch("workflows.base.run_workflow") as mock_rw:
            mock_rw.return_value = {
                "status": "success",
                "commit_sha": "def456",
                "branch_name": "feat-x",
                "modified_files": ["c.py"],
                "tdd_status": "passed",
                "tdd_iteration": 1,
                "verification_passed": True,
            }
            result = run_autocode_agent("test task")
        assert "artifacts" in result, "Result must include structured artifacts"
        assert result["artifacts"]["commit_sha"] == "def456"
        assert result["artifacts"]["branch_name"] == "feat-x"
        assert result["artifacts"]["modified_files"] == ["c.py"]


# ─── #46: Multi-file git-diff input ────────────────────────────────────────

class TestGitDiffInput:
    """[#46] files={'all changed': ''} + git_diff=True resolves via git diff."""

    def test_no_git_diff_returns_files_as_is(self):
        from workflows.autocode import _resolve_files_input
        files = {"a.py": "content", "b.py": "more"}
        result = _resolve_files_input(files, git_diff=False)
        assert result == files

    def test_git_diff_false_ignores_all_changed_key(self):
        """Without git_diff=True, 'all changed' is just stripped (not resolved)."""
        from workflows.autocode import _resolve_files_input
        result = _resolve_files_input({"all changed": "", "a.py": "content"}, git_diff=False)
        assert result == {"a.py": "content"}

    def test_git_diff_true_resolves_changed_files(self, tmp_path, mocker):
        """[#46] git_diff=True + 'all changed' reads git diff --name-only."""
        from workflows.autocode import _resolve_files_input
        # Create a file that "git diff" would report — in tmp_path so exists() works
        changed_file = tmp_path / "changed.py"
        changed_file.write_text("print('hello')", encoding="utf-8")

        # Mock subprocess.run to return our changed file
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "changed.py\n"
        mocker.patch("subprocess.run", return_value=mock_result)

        # Change to tmp_path so Path("changed.py").exists() resolves there
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _resolve_files_input({"all changed": ""}, git_diff=True)
        finally:
            os.chdir(old_cwd)
        assert "changed.py" in result
        assert result["changed.py"] == "print('hello')"

    def test_git_diff_merges_explicit_files(self, tmp_path, mocker):
        """[#46] Explicitly-passed files merge with git-diff results."""
        from workflows.autocode import _resolve_files_input
        # Create the diff file in tmp_path
        (tmp_path / "diff_file.py").write_text("content", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff_file.py\n"
        mocker.patch("subprocess.run", return_value=mock_result)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _resolve_files_input(
                {"all changed": "", "explicit.py": "explicit content"},
                git_diff=True,
            )
        finally:
            os.chdir(old_cwd)
        assert "diff_file.py" in result
        assert "explicit.py" in result
        assert result["explicit.py"] == "explicit content"

    def test_git_diff_failure_returns_empty(self, mocker):
        """If git diff fails, return empty (graceful degradation)."""
        from workflows.autocode import _resolve_files_input
        mocker.patch("subprocess.run", side_effect=Exception("git not found"))
        result = _resolve_files_input({"all changed": ""}, git_diff=True)
        assert result == {}


# ─── #47: Dry-run guards ───────────────────────────────────────────────────

class TestDryRunGuards:
    """[#47] dry_run=True must skip all mutations (write_files, commit, branch)."""

    def test_write_files_skips_on_dry_run(self):
        """[#47] node_write_files must return early when dry_run=True."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        state = {
            "dry_run": True,
            "tdd_source_code": '{"patches": []}',  # would normally trigger writes
            "trace_id": "t1",
        }
        result = node_write_files(state)
        assert result["status"] == "dry_run"
        assert result["modified_files"] == []

    def test_write_files_proceeds_without_dry_run(self):
        """Without dry_run, write_files proceeds (and may fail on bad JSON, etc.)."""
        from workflows.autocode_impl.nodes.write_files import node_write_files
        state = {
            "dry_run": False,
            "tdd_source_code": '{"patches": []}',
            "trace_id": "t1",
        }
        # This will proceed past the dry_run guard. With empty patches it
        # should complete without error.
        result = node_write_files(state)
        # Just assert it didn't return the dry_run status
        assert result.get("status") != "dry_run"

    def test_commit_skips_on_dry_run(self):
        """[#47] node_commit must skip the git commit when dry_run=True."""
        from workflows.autocode_impl.nodes.commit import node_commit
        with patch("workflows.autocode_impl.git_ops._git_commit") as mock_git:
            state = {
                "dry_run": True,
                "verification_passed": True,
                "plan": [],
                "task": "test",
                "task_type": "feature",
                "trace_id": "t1",
            }
            result = node_commit(state)
        assert result["status"] == "dry_run"
        assert result["commit_sha"] == "(dry-run)"
        assert not mock_git.called, "git commit must NOT be called in dry-run mode"

    def test_branch_skips_on_dry_run(self):
        """[#47] node_git_branch must skip branch creation when dry_run=True."""
        from workflows.autocode_impl.nodes.branch import node_git_branch
        with patch("workflows.autocode_impl.git_ops._git_create_branch") as mock_branch:
            state = {
                "dry_run": True,
                "branch": "feat-x",
                "trace_id": "t1",
            }
            result = node_git_branch(state)
        assert result == {}
        assert not mock_branch.called, "git branch creation must NOT run in dry-run mode"

    def test_commit_proceeds_without_dry_run(self, mocker):
        """Without dry_run, commit proceeds normally."""
        from workflows.autocode_impl.nodes.commit import node_commit
        # Patch at the source module (commit.py imports _git_commit at top level)
        mock_git_commit = mocker.patch(
            "workflows.autocode_impl.nodes.commit._git_commit", return_value="abc123"
        )
        state = {
            "dry_run": False,
            "verification_passed": True,
            "plan": [],
            "task": "test",
            "task_type": "feature",
            "trace_id": "t1",
        }
        result = node_commit(state)
        assert mock_git_commit.called, "git commit must run when dry_run=False"
        assert result["commit_sha"] == "abc123"
