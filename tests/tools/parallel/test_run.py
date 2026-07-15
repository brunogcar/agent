"""Tests for the 'run' action of the parallel meta-tool.

Covers:
  - Input validation (bad types, missing fields, unknown tools)
  - Parallel-safe enforcement + allow_unsafe override
  - Successful concurrent execution
  - Error capture for failing tools
  - trace_id threading
  - duration_ms presence
  - timeout override + default fallback to cfg.worker_timeout
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from tools.parallel import parallel
from tools.parallel_ops.tool_map import _TOOL_MAP, PARALLEL_SAFE


# =============================================================================
# Test Input Validation
# =============================================================================
class TestRunValidation:
    def test_tasks_must_be_list(self):
        result = parallel(action="run", tasks="not a list")
        assert result["status"] == "error"
        assert "must be a list" in result["error"]

    def test_empty_tasks(self):
        result = parallel(action="run", tasks=[])
        assert result["status"] == "error"
        assert "No tasks provided" in result["error"]

    def test_spec_must_be_dict(self):
        result = parallel(action="run", tasks=["not a dict"])
        assert result["status"] == "error"
        assert "must be a dict" in result["error"]

    def test_missing_name(self):
        result = parallel(action="run", tasks=[{"args": {}}])
        assert result["status"] == "error"
        assert "missing 'name'" in result["error"]

    def test_unknown_tool(self):
        # "nonexistent" is not in _TOOL_MAP — _get_tool_fn returns None.
        result = parallel(action="run", tasks=[{"name": "nonexistent", "args": {}}])
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_args_must_be_dict(self):
        # Pre-populate _TOOL_MAP so we reach the args-type check.
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="run", tasks=[{"name": "web", "args": "not a dict"}])
        assert result["status"] == "error"
        assert "args must be a dict" in result["error"]


# =============================================================================
# Test Parallel-Safe Enforcement
# =============================================================================
class TestRunParallelSafe:
    def test_unsafe_tool_blocked(self):
        mock_fn = MagicMock()
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(action="run", tasks=[{"name": "unsafe_tool", "args": {}}])
            assert result["status"] == "error"
            assert "not parallel-safe" in result["error"]

    def test_allow_unsafe_override(self):
        mock_fn = MagicMock(return_value={"status": "success", "data": "ok"})
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(
                action="run",
                tasks=[{"name": "unsafe_tool", "args": {}}],
                allow_unsafe=True,
            )
            assert result["status"] == "success"
            assert result["data"]["completed"] == 1


# =============================================================================
# Test Parallel Execution
# =============================================================================
class TestRunExecution:
    def test_two_tools_run(self, mock_cfg):
        mock_web = MagicMock(return_value={"status": "success", "data": "web ok"})
        mock_file = MagicMock(return_value={"status": "success", "data": "file ok"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "file": mock_file}, clear=False):
            result = parallel(action="run", tasks=[
                {"name": "web", "args": {"action": "search", "query": "test"}},
                {"name": "file", "args": {"action": "list_directory", "path": "."}},
            ])
            assert result["status"] == "success"
            assert result["data"]["completed"] == 2
            assert result["data"]["failed"] == 0
            assert len(result["data"]["results"]) == 2
            mock_web.assert_called_once_with(action="search", query="test")
            mock_file.assert_called_once_with(action="list_directory", path=".")

    def test_tool_error_captured(self, mock_cfg):
        mock_fn = MagicMock(side_effect=RuntimeError("boom"))
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="run", tasks=[{"name": "web", "args": {}}])
            assert result["status"] == "success"
            assert result["data"]["failed"] == 1
            assert result["data"]["errors"][0]["tool"] == "web"
            assert "boom" in result["data"]["errors"][0]["error"]

    def test_trace_id_passed(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(
                action="run",
                tasks=[{"name": "web", "args": {}}],
                trace_id="trace-123",
            )
            assert result.get("trace_id") == "trace-123"
            # Each result entry should also carry trace_id
            assert result["data"]["results"][0]["trace_id"] == "trace-123"

    def test_duration_ms_present(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="run", tasks=[{"name": "web", "args": {}}])
            assert result["status"] == "success"
            # duration_ms lives at both the facade envelope and the executor data level
            assert "duration_ms" in result
            assert isinstance(result["duration_ms"], (int, float))
            assert "duration_ms" in result["data"]
            assert result["duration_ms"] >= 0

    def test_timeout_uses_cfg_when_negative(self, mock_cfg):
        """timeout=-1 (default) should fall back to cfg.worker_timeout."""
        mock_cfg.worker_timeout = 42
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            # We can't easily assert the timeout value reached ThreadPoolExecutor,
            # but we can confirm the call succeeds (no exception from cfg access).
            result = parallel(action="run", tasks=[{"name": "web", "args": {}}])
            assert result["status"] == "success"

    def test_timeout_explicit_override(self, mock_cfg):
        """A non-negative timeout should bypass cfg.worker_timeout."""
        mock_cfg.worker_timeout = -999  # sentinel; if used, dispatch would break
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(
                action="run",
                tasks=[{"name": "web", "args": {}}],
                timeout=30,
            )
            assert result["status"] == "success"

    def test_max_workers_clamped(self, mock_cfg):
        """max_workers > 8 should be clamped to 8 (not crash)."""
        mocks = {f"web_{i}": MagicMock(return_value={"status": "success"}) for i in range(10)}
        # Reuse 'web' as one of the tools; others use unique names so they need
        # to be added to PARALLEL_SAFE via patch. Simpler: just use 'web' repeatedly.
        # But each task has same name → tool fn called 10x. Use 10 distinct mock names
        # that are NOT in PARALLEL_SAFE and enable allow_unsafe.
        with patch.dict(_TOOL_MAP, mocks, clear=False):
            with patch("tools.parallel_ops.actions.run.PARALLEL_SAFE", frozenset(mocks.keys())):
                tasks = [{"name": n, "args": {}} for n in mocks.keys()]
                result = parallel(action="run", tasks=tasks, max_workers=100, allow_unsafe=True)
                assert result["status"] == "success"
                assert result["data"]["completed"] == 10
