"""Tests for the python run_data action (controlled imports).

Mirrors the structure of tests/tools/consult/test_advise.py. Covers:
  1. Stdlib imports → in-process execution
  2. Heavy imports → subprocess execution (mocked)
  3. Blocked imports (os, subprocess, etc.) → security boundary
  4. Imports not in allowed list → rejected
  5. Syntax errors → clean fail
  6. timeout override → forwarded to _run_subprocess

Subprocess tests mock subprocess.run to avoid actually spinning up a Python
subprocess (slow + fragile in CI). In-process tests run for real because
stdlib imports are safe and fast.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.python import python


class TestRunDataStdlibInProcess:
    """run_data: stdlib imports run in-process (mode='in_process')."""

    def test_json_imports_in_process(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import json\nprint(json.dumps({'a': 1}))")
        assert result["status"] == "success"
        assert result["mode"] == "in_process"
        assert '"a": 1' in result["data"] or '"a":1' in result["data"]

    def test_math_imports_in_process(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import math\nprint(math.sqrt(16))")
        assert result["status"] == "success"
        assert result["mode"] == "in_process"
        assert "4" in result["data"]

    def test_multiple_stdlib_imports(self, mock_cfg, mock_pruner):
        code = "import json, math\nprint(json.dumps({'sqrt': math.sqrt(9)}))"
        result = python(action="run_data", code=code)
        assert result["status"] == "success"
        assert result["mode"] == "in_process"
        assert "3" in result["data"]

    def test_from_import_stdlib(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="from datetime import datetime\nprint(datetime(2024,1,1).year)")
        assert result["status"] == "success"
        assert result["mode"] == "in_process"
        assert "2024" in result["data"]


class TestRunDataHeavySubprocess:
    """run_data: heavy imports route to subprocess (mode='subprocess')."""

    def test_pandas_routes_to_subprocess(self, mock_cfg, mock_pruner, temp_workspace):
        """pandas is a heavy import — should call _run_subprocess."""
        mock_cfg.workspace_root = temp_workspace
        mock_cfg.execution_timeout = 30

        fake_completed = MagicMock(stdout="42\n", stderr="", returncode=0)
        with patch("tools.python_ops.actions.run_data._run_subprocess") as mock_sub:
            mock_sub.return_value = {
                "status": "success",
                "data": "42",
                "mode": "subprocess",
            }
            result = python(action="run_data", code="import pandas\nprint(42)")

        assert result["status"] == "success"
        # _run_subprocess was invoked with the code and default timeout_override=-1.
        mock_sub.assert_called_once()
        call_args, call_kwargs = mock_sub.call_args
        assert "import pandas" in call_args[0]
        assert call_kwargs.get("timeout_override") == -1

    def test_numpy_routes_to_subprocess(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.run_data._run_subprocess") as mock_sub:
            mock_sub.return_value = {"status": "success", "data": "ok", "mode": "subprocess"}
            python(action="run_data", code="import numpy as np\nprint(np.array([1,2]))")
        mock_sub.assert_called_once()

    def test_subprocess_failure_surfaces_error(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.run_data._run_subprocess") as mock_sub:
            mock_sub.return_value = {
                "status": "error",
                "data": None,
                "error": "ModuleNotFoundError: No module named 'pandas'",
                "mode": "subprocess",
            }
            result = python(action="run_data", code="import pandas\nprint(pandas.__version__)")
        assert result["status"] == "error"
        assert "ModuleNotFoundError" in result["error"]


class TestRunDataBlockedImports:
    """run_data: BLOCKED_IMPORTS rejected for security."""

    def test_os_blocked(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import os\nprint(os.getcwd())")
        assert result["status"] == "error"
        assert "Import(s) blocked for security" in result["error"]
        assert "os" in result["error"]

    def test_subprocess_blocked(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import subprocess\nprint('hacked')")
        assert result["status"] == "error"
        assert "Import(s) blocked for security" in result["error"]

    def test_socket_blocked(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import socket\nprint('net')")
        assert result["status"] == "error"
        assert "Import(s) blocked for security" in result["error"]

    def test_pickle_blocked(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import pickle\nprint('ser')")
        assert result["status"] == "error"
        assert "Import(s) blocked for security" in result["error"]


class TestRunDataUnknownImports:
    """run_data: imports not in ALL_ALLOWED rejected."""

    def test_requests_not_allowed(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import requests\nprint('web')")
        assert result["status"] == "error"
        assert "Import(s) not in allowed list" in result["error"]
        assert "requests" in result["error"]

    def test_psutil_not_allowed(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import psutil\nprint('proc')")
        assert result["status"] == "error"
        assert "Import(s) not in allowed list" in result["error"]


class TestRunDataSyntaxError:
    """run_data: syntax errors are caught and surfaced cleanly."""

    def test_syntax_error_returns_clean_fail(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="import json\nprint(json.dumps({)")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]

    def test_incomplete_code_syntax_error(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="def f(:")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]


class TestRunDataTimeoutOverride:
    """run_data: timeout param is forwarded to _run_subprocess."""

    def test_timeout_override_forwarded(self, mock_cfg, mock_pruner, temp_workspace):
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.run_data._run_subprocess") as mock_sub:
            mock_sub.return_value = {"status": "success", "data": "ok", "mode": "subprocess"}
            python(action="run_data", code="import pandas\nprint(42)", timeout=120)
        call_args, call_kwargs = mock_sub.call_args
        assert call_kwargs.get("timeout_override") == 120

    def test_timeout_default_negative_one(self, mock_cfg, mock_pruner, temp_workspace):
        """Default timeout=-1 should pass through as -1 (use cfg default)."""
        mock_cfg.workspace_root = temp_workspace
        with patch("tools.python_ops.actions.run_data._run_subprocess") as mock_sub:
            mock_sub.return_value = {"status": "success", "data": "ok", "mode": "subprocess"}
            python(action="run_data", code="import pandas\nprint(42)")
        call_args, call_kwargs = mock_sub.call_args
        assert call_kwargs.get("timeout_override") == -1


class TestRunDataEmptyCode:
    """run_data: empty code is rejected."""

    def test_empty_code_rejected(self, mock_cfg, mock_pruner):
        result = python(action="run_data", code="")
        assert result["status"] == "error"
        assert "No code provided" in result["error"]


class TestRunDataTraceID:
    """run_data: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_pruner):
        result = python(
            action="run_data",
            code="import json\nprint(json.dumps({'x': 1}))",
            trace_id="trace-rd-1",
        )
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-rd-1"
