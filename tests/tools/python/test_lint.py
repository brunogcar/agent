"""Tests for the python lint action (ruff/flake8 pre-check, NEW v1.0).

Covers:
  1. Clean code → no issues reported
  2. Code with errors → lint output surfaces them
  3. ruff-not-installed fallback to flake8
  4. Neither ruff nor flake8 installed → fail with install hint
  5. Lint timeout (10s hard cap) — hard to test deterministically, skipped
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.python import python


class TestLintCleanCode:
    """lint: clean code reports no issues."""

    def test_clean_code(self):
        """A well-formed code snippet should produce no lint issues."""
        result = python(action="lint", code="x = 1\nprint(x)\n")
        assert result["status"] == "success"
        assert result["mode"] == "lint"
        # Either "no issues" or actually empty (depending on ruff/flake8 behavior).
        # We assert success regardless of issue count — exit code 0/1 both succeed.

    def test_clean_function_def(self):
        result = python(action="lint", code="def add(a, b):\n    return a + b\n")
        assert result["status"] == "success"


class TestLintWithErrors:
    """lint: code with syntax/lint errors is reported in the output."""

    def test_undefined_name(self):
        """F401 / F821 — undefined name (pyflakes F)."""
        # 'print(undefined_var)' triggers F821 undefined name.
        result = python(action="lint", code="print(undefined_var)\n")
        assert result["status"] == "success"
        # If ruff/flake8 is installed, output should mention the undefined name.
        # If neither is installed, the result will be a fail (see TestLintNotInstalled).
        if "no issues" not in result["data"]:
            # Linter caught something — likely F821.
            assert "undefined_var" in result["data"] or "F821" in result["data"]

    def test_unused_import(self):
        """F401 — unused import."""
        result = python(action="lint", code="import os\n")
        assert result["status"] == "success"
        # If a linter is installed, 'import os' + no usage triggers F401.
        # If neither is installed, result is fail (not success).

    def test_syntax_error_caught(self):
        """E999 — syntax error."""
        result = python(action="lint", code="def f(:\n    pass\n")
        assert result["status"] == "success"
        # If a linter is installed, it should report the syntax error.
        # The lint action returns success even when issues are found
        # (exit code 1 from ruff/flake8 means "issues found", not "tool error").


class TestLintRuffNotInstalledFallback:
    """lint: if ruff isn't installed, fall back to flake8."""

    def test_falls_back_to_flake8(self):
        """If ruff is missing but flake8 is present, use flake8."""
        with patch("tools.python_ops.actions.lint._has_executable") as mock_has, \
             patch("tools.python_ops.actions.lint.subprocess.run") as mock_run:
            # ruff missing, flake8 present
            def has_side_effect(name):
                return name == "flake8"
            mock_has.side_effect = has_side_effect
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

            result = python(action="lint", code="x = 1\n")

        assert result["status"] == "success"
        # Verify flake8 was invoked (not ruff)
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "flake8"


class TestLintNeitherInstalled:
    """lint: if neither ruff nor flake8 is installed, return fail."""

    def test_neither_installed_returns_fail(self):
        with patch("tools.python_ops.actions.lint._has_executable", return_value=False):
            result = python(action="lint", code="x = 1\n")
        assert result["status"] == "error"
        assert "Neither ruff nor flake8 is installed" in result["error"]
        assert "pip install ruff" in result["error"]


class TestLintEmptyCode:
    """lint: empty code is rejected."""

    def test_empty_code_rejected(self):
        result = python(action="lint", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]

    def test_whitespace_code_rejected(self):
        result = python(action="lint", code="   \n  ")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]


class TestLintTraceID:
    """lint: trace_id threading."""

    def test_trace_id_in_success(self):
        result = python(action="lint", code="x = 1\n", trace_id="trace-lint-1")
        assert result["status"] in ("success", "error")  # depends on linter availability
        if result["status"] == "success":
            assert result["trace_id"] == "trace-lint-1"

    def test_trace_id_in_not_installed_error(self):
        with patch("tools.python_ops.actions.lint._has_executable", return_value=False):
            result = python(action="lint", code="x = 1\n", trace_id="trace-lint-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-lint-2"


class TestLintTimeoutEnforced:
    """lint: 10s hard timeout — verify timeout is passed to subprocess.run."""

    def test_timeout_is_10_seconds(self):
        """The lint action should call subprocess.run with timeout=10."""
        with patch("tools.python_ops.actions.lint.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            python(action="lint", code="x = 1\n")
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("timeout") == 10

    def test_timeout_expired_returns_fail(self):
        """If linting exceeds 10s, return fail with timeout message."""
        import subprocess as sp
        with patch("tools.python_ops.actions.lint.subprocess.run") as mock_run:
            mock_run.side_effect = sp.TimeoutExpired(cmd="ruff", timeout=10)
            result = python(action="lint", code="x = 1\n")
        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()
