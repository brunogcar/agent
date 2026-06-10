"""tests/tools/parallel/test_parallel.py
Unit tests for the parallel tool and core parallel executor.

Covers:
- Input validation (bad types, missing fields, unknown tools)
- Parallel-safe enforcement
- Successful concurrent execution
- Error handling in parallel runs
- max_workers bounds
"""

import pytest
from unittest.mock import patch, MagicMock

from tools.parallel import parallel, _TOOL_MAP, PARALLEL_SAFE
from core.parallel_executor import dispatch_parallel


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def mock_tools():
    """Return mock functions for common parallel-safe tools."""
    return {
        "web": MagicMock(return_value={"status": "success", "data": "web ok"}),
        "git": MagicMock(return_value={"status": "success", "data": "git ok"}),
        "file": MagicMock(return_value={"status": "success", "data": "file ok"}),
    }


# =============================================================================
# Test Input Validation
# =============================================================================
class TestValidation:
    def test_tools_must_be_list(self):
        result = parallel(tools="not a list")
        assert result["status"] == "error"
        assert "must be a list" in result["error"]

    def test_empty_tools(self):
        result = parallel(tools=[])
        assert result["status"] == "error"
        assert "No tools provided" in result["error"]

    def test_spec_must_be_dict(self):
        result = parallel(tools=["not a dict"])
        assert result["status"] == "error"
        assert "must be a dict" in result["error"]

    def test_missing_name(self):
        result = parallel(tools=[{"args": {}}])
        assert result["status"] == "error"
        assert "missing 'name'" in result["error"]

    def test_unknown_tool(self):
        result = parallel(tools=[{"name": "nonexistent", "args": {}}])
        assert result["status"] == "error"
        assert "not found" in result["error"]


# =============================================================================
# Test Parallel-Safe Enforcement
# =============================================================================
class TestParallelSafe:
    def test_unsafe_tool_blocked(self):
        mock_fn = MagicMock()
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(tools=[{"name": "unsafe_tool", "args": {}}])
            assert result["status"] == "error"
            assert "not parallel-safe" in result["error"]

    def test_allow_unsafe_override(self):
        mock_fn = MagicMock(return_value={"status": "success", "data": "ok"})
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(
                tools=[{"name": "unsafe_tool", "args": {}}],
                allow_unsafe=True,
            )
            assert result["status"] == "success"
            assert result["data"]["completed"] == 1


# =============================================================================
# Test Parallel Execution (Tool Wrapper)
# =============================================================================
class TestParallelExecution:
    def test_two_tools_run(self, mock_tools):
        with patch.dict(_TOOL_MAP, mock_tools, clear=False):
            result = parallel(tools=[
                {"name": "web", "args": {"action": "search", "query": "test"}},
                {"name": "file", "args": {"action": "list", "path": "."}},
            ])

            assert result["status"] == "success"
            assert result["data"]["completed"] == 2
            assert result["data"]["failed"] == 0
            assert len(result["data"]["results"]) == 2

            mock_tools["web"].assert_called_once_with(action="search", query="test")
            mock_tools["file"].assert_called_once_with(action="list", path=".")

    def test_tool_error_captured(self):
        mock_fn = MagicMock(side_effect=RuntimeError("boom"))
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(tools=[{"name": "web", "args": {}}])
            assert result["status"] == "success"
            assert result["data"]["failed"] == 1
            assert result["data"]["errors"][0]["tool"] == "web"
            assert "boom" in result["data"]["errors"][0]["error"]

    def test_trace_id_passed(self):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(tools=[{"name": "web", "args": {}}], trace_id="trace-123")
            assert result.get("trace_id") == "trace-123"


# =============================================================================
# Test Core Executor Engine
# =============================================================================
class TestExecutorEngine:
    def test_empty_calls(self):
        result = dispatch_parallel([])
        assert result["status"] == "error"
        assert "No calls" in result["error"]

    def test_single_call(self):
        mock_fn = MagicMock(return_value={"status": "success", "data": "ok"})
        result = dispatch_parallel([("test", mock_fn, {"arg": 1})])
        assert result["status"] == "success"
        assert result["data"]["completed"] == 1
        assert result["data"]["failed"] == 0
        mock_fn.assert_called_once_with(arg=1)

    def test_max_workers_extreme(self):
        """Verify executor doesn't crash with high max_workers (capped internally)."""
        mocks = [(f"tool_{i}", MagicMock(return_value={"status": "success"}), {}) for i in range(10)]
        result = dispatch_parallel(mocks, max_workers=100)
        assert result["status"] == "success"
        assert result["data"]["completed"] == 10

    def test_result_wrapping(self):
        """Verify each result is wrapped with tool name and status."""
        mock_fn = MagicMock(return_value={"status": "success", "data": "payload"})
        result = dispatch_parallel([("web", mock_fn, {})])
        assert result["status"] == "success"
        wrapped = result["data"]["results"][0]
        assert wrapped["tool"] == "web"
        assert wrapped["status"] == "success"
        assert wrapped["result"] == {"status": "success", "data": "payload"}

    def test_error_wrapping(self):
        mock_fn = MagicMock(side_effect=ValueError("bad arg"))
        result = dispatch_parallel([("file", mock_fn, {})])
        assert result["status"] == "success"
        assert result["data"]["failed"] == 1
        err = result["data"]["errors"][0]
        assert err["tool"] == "file"
        assert "bad arg" in err["error"]
