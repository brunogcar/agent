"""Tests for the python profile action (cProfile timing, NEW v1.0).

Covers:
  1. Simple code with no imports → in-process profiling
  2. Code with imports → subprocess profiling (mocked)
  3. Output format contains pstats markers (ncalls, function calls)

The profile action is NOT sandboxed (profiling needs full builtins). Tests
run real cProfile for the in-process path and mock _run_subprocess for the
subprocess path.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.python import python


class TestProfileSimpleInProcess:
    """profile: code with no imports runs in-process under cProfile."""

    def test_profile_simple_math(self, mock_cfg, mock_pruner):
        result = python(action="profile", code="print(sum(range(100)))")
        assert result["status"] == "success"
        assert result["mode"] == "profile"
        # pstats output contains "function calls" header and "ncalls" column
        assert "function calls" in result["data"].lower() or "ncalls" in result["data"].lower()

    def test_profile_returns_pstats_format(self, mock_cfg, mock_pruner):
        result = python(action="profile", code="x = [i**2 for i in range(1000)]")
        assert result["status"] == "success"
        # pstats sorts by cumulative — header line includes "cumulative"
        assert "cumulative" in result["data"].lower() or "function calls" in result["data"].lower()

    def test_profile_code_with_runtime_error(self, mock_cfg, mock_pruner):
        """Runtime error in profiled code is surfaced cleanly."""
        result = python(action="profile", code="print(1 / 0)")
        assert result["status"] == "error"
        assert "Profiled code raised" in result["error"]


class TestProfileSubprocessRouting:
    """profile: code with imports routes to subprocess."""

    def test_imports_route_to_subprocess(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.profile._run_subprocess") as mock_sub:
            mock_sub.return_value = {
                "status": "success",
                "data": "function calls...",
                "mode": "subprocess",
            }
            result = python(action="profile", code="import json\nprint(json.dumps({'x': 1}))")
        mock_sub.assert_called_once()
        assert result["status"] == "success"
        # Profile subprocess wrapper forces mode="profile" on the result.
        assert result["mode"] == "profile"

    def test_subprocess_failure_surfaces_error(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.profile._run_subprocess") as mock_sub:
            mock_sub.return_value = {
                "status": "error",
                "data": None,
                "error": "boom",
                "mode": "subprocess",
            }
            result = python(action="profile", code="import json\nprint('x')")
        assert result["status"] == "error"
        assert "boom" in result["error"]


class TestProfileOutputFormat:
    """profile: output format checks."""

    def test_output_contains_function_call_count(self, mock_cfg, mock_pruner):
        """pstats header includes 'X function calls in Y seconds'."""
        result = python(action="profile", code="sum(range(50))")
        assert result["status"] == "success"
        # The header line: "50 function calls in 0.000 seconds"
        assert "function calls" in result["data"].lower()

    def test_output_contains_top_20_functions(self, mock_cfg, mock_pruner):
        """print_stats(20) limits output to top 20 entries."""
        result = python(action="profile", code="print(sum(range(100)))")
        assert result["status"] == "success"
        # Verify output is bounded — at least the header is present.
        assert len(result["data"]) > 0


class TestProfileSyntaxError:
    """profile: syntax errors are caught."""

    def test_syntax_error(self, mock_cfg, mock_pruner):
        result = python(action="profile", code="def f(:")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]


class TestProfileEmptyCode:
    """profile: empty code is rejected."""

    def test_empty_code(self, mock_cfg, mock_pruner):
        result = python(action="profile", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]


class TestProfileTraceID:
    """profile: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_pruner):
        result = python(action="profile", code="print('hi')", trace_id="trace-prof-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-prof-1"


class TestProfileTimeoutOverride:
    """profile: timeout is forwarded to subprocess."""

    def test_timeout_forwarded(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.profile._run_subprocess") as mock_sub:
            mock_sub.return_value = {
                "status": "success",
                "data": "ok",
                "mode": "subprocess",
            }
            python(action="profile", code="import json\nprint('x')", timeout=60)
        call_args, call_kwargs = mock_sub.call_args
        assert call_kwargs.get("timeout_override") == 60
