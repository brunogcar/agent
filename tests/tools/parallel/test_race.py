"""Tests for the 'race' action of the parallel meta-tool.

Covers:
  - First successful result wins (mocks with different delays)
  - All tasks fail → winner is None (envelope still 'success')
  - Failed tasks captured in `failed` list
  - trace_id threading
  - Validation (delegates to shared _validate_tasks, so light coverage here)
  - PARALLEL_SAFE enforcement + allow_unsafe override
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from tools.parallel import parallel
from tools.parallel_ops.tool_map import _TOOL_MAP


class TestRaceValidation:
    def test_empty_tasks(self):
        result = parallel(action="race", tasks=[])
        assert result["status"] == "error"
        assert "No tasks provided" in result["error"]

    def test_unknown_tool(self):
        result = parallel(action="race", tasks=[{"name": "nonexistent", "args": {}}])
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_unsafe_tool_blocked(self):
        mock_fn = MagicMock()
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(action="race", tasks=[{"name": "unsafe_tool", "args": {}}])
            assert result["status"] == "error"
            assert "not parallel-safe" in result["error"]


class TestRaceExecution:
    def test_first_success_wins(self, mock_cfg):
        """Fastest successful mock should be declared the winner."""
        # Mock with no delay beats mock with delay, regardless of submission order.
        fast = MagicMock(return_value={"status": "success", "data": "fast"})
        slow = MagicMock(side_effect=lambda: (
            time.sleep(0.05) or {"status": "success", "data": "slow"}
        ))
        with patch.dict(_TOOL_MAP, {"web": fast, "file": slow}, clear=False):
            result = parallel(action="race", tasks=[
                {"name": "file", "args": {}},  # submitted first, slow
                {"name": "web", "args": {}},   # submitted second, fast
            ])
            assert result["status"] == "success"
            winner = result["data"]["winner"]
            assert winner is not None
            assert winner["tool"] == "web"
            assert winner["result"]["data"] == "fast"

    def test_all_fail_returns_none_winner(self, mock_cfg):
        """If every task fails, winner is None and envelope status is still 'success'."""
        failing = MagicMock(side_effect=RuntimeError("nope"))
        with patch.dict(_TOOL_MAP, {"web": failing, "file": failing}, clear=False):
            result = parallel(action="race", tasks=[
                {"name": "web", "args": {}},
                {"name": "file", "args": {}},
            ])
            assert result["status"] == "success"  # race itself succeeded
            assert result["data"]["winner"] is None
            assert len(result["data"]["failed"]) == 2

    def test_status_error_result_treated_as_failure(self, mock_cfg):
        """A result with status='error' does NOT win the race."""
        ok_mock = MagicMock(return_value={"status": "success", "data": "ok"})
        err_mock = MagicMock(return_value={"status": "error", "error": "bad"})
        with patch.dict(_TOOL_MAP, {"web": ok_mock, "file": err_mock}, clear=False):
            result = parallel(action="race", tasks=[
                {"name": "file", "args": {}},
                {"name": "web", "args": {}},
            ])
            assert result["status"] == "success"
            winner = result["data"]["winner"]
            assert winner is not None
            assert winner["tool"] == "web"

    def test_trace_id_threaded(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(
                action="race",
                tasks=[{"name": "web", "args": {}}],
                trace_id="race-trace-1",
            )
            assert result.get("trace_id") == "race-trace-1"
            winner = result["data"]["winner"]
            assert winner["trace_id"] == "race-trace-1"

    def test_duration_ms_present(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="race", tasks=[{"name": "web", "args": {}}])
            assert "duration_ms" in result
            assert result["duration_ms"] >= 0

    def test_single_task_race(self, mock_cfg):
        """Race with one task should succeed if that task succeeds."""
        mock_fn = MagicMock(return_value={"status": "success", "data": "solo"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="race", tasks=[{"name": "web", "args": {}}])
            assert result["status"] == "success"
            assert result["data"]["winner"]["tool"] == "web"
            assert result["data"]["failed"] == []
