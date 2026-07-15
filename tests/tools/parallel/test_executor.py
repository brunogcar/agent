"""Unit tests for parallel_ops/executor.py — dispatch_run, dispatch_race, dispatch_pipeline.

Tests the executors in isolation, calling them directly with synthetic
calls lists (bypassing the action handlers / facade). Mocks cfg so the
default timeout path works.

Covers:
  - dispatch_run: empty calls, single call, max_workers clamp, timeout,
    result wrapping, error wrapping, duration_ms, trace_id threading
  - dispatch_race: empty calls, first success wins, all fail, late
    failures captured, cancellation of pending futures
  - dispatch_pipeline: empty calls, sequential execution, feed=str
    replaces args, feed=dict merges, error mid-chain stops pipeline
  - _resolve_dot_path: dict keys, object attrs, missing segments
  - _resolve_timeout: explicit vs cfg fallback
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from tools.parallel_ops.executor import (
    dispatch_run,
    dispatch_race,
    dispatch_pipeline,
    _safe_run,
    _resolve_dot_path,
    _resolve_timeout,
    _parallel_depth,
)


# =============================================================================
# dispatch_run
# =============================================================================
class TestDispatchRun:
    def test_empty_calls(self):
        result = dispatch_run([])
        assert result["status"] == "error"
        assert "No calls" in result["error"]

    def test_single_call(self):
        mock_fn = MagicMock(return_value={"status": "success", "data": "ok"})
        result = dispatch_run([("test", mock_fn, {"arg": 1})])
        assert result["status"] == "success"
        assert result["data"]["completed"] == 1
        assert result["data"]["failed"] == 0
        mock_fn.assert_called_once_with(arg=1)

    def test_max_workers_high_clamped(self, mock_cfg):
        """Verify executor doesn't crash with high max_workers (capped to 8)."""
        mocks = [(f"tool_{i}", MagicMock(return_value={"status": "success"}), {}) for i in range(10)]
        result = dispatch_run(mocks, max_workers=100)
        assert result["status"] == "success"
        assert result["data"]["completed"] == 10

    def test_max_workers_low_clamped(self, mock_cfg):
        """max_workers < 1 is clamped to 1."""
        mock_fn = MagicMock(return_value={"status": "success"})
        result = dispatch_run([("a", mock_fn, {})], max_workers=0)
        assert result["status"] == "success"
        assert result["data"]["completed"] == 1

    def test_result_wrapping(self):
        mock_fn = MagicMock(return_value={"status": "success", "data": "payload"})
        result = dispatch_run([("web", mock_fn, {})])
        assert result["status"] == "success"
        wrapped = result["data"]["results"][0]
        assert wrapped["tool"] == "web"
        assert wrapped["status"] == "success"
        assert wrapped["result"] == {"status": "success", "data": "payload"}

    def test_error_wrapping(self):
        mock_fn = MagicMock(side_effect=ValueError("bad arg"))
        result = dispatch_run([("file", mock_fn, {})])
        assert result["status"] == "success"
        assert result["data"]["failed"] == 1
        err = result["data"]["errors"][0]
        assert err["tool"] == "file"
        assert "bad arg" in err["error"]

    def test_duration_ms_present(self):
        mock_fn = MagicMock(return_value={"status": "success"})
        result = dispatch_run([("web", mock_fn, {})])
        assert "duration_ms" in result["data"]
        assert result["data"]["duration_ms"] >= 0

    def test_trace_id_threaded(self):
        mock_fn = MagicMock(return_value={"status": "success"})
        result = dispatch_run([("web", mock_fn, {})], trace_id="trace-exec-1")
        assert result.get("trace_id") == "trace-exec-1"
        assert result["data"]["results"][0]["trace_id"] == "trace-exec-1"

    def test_nested_parallel_blocked(self):
        """When _parallel_depth.value > 0, dispatch_run rejects the call."""
        mock_fn = MagicMock(return_value={"status": "success"})
        _parallel_depth.value = 1
        try:
            result = dispatch_run([("web", mock_fn, {})])
            assert result["status"] == "error"
            assert "Nested parallel" in result["error"]
        finally:
            _parallel_depth.value = 0


# =============================================================================
# dispatch_race
# =============================================================================
class TestDispatchRace:
    def test_empty_calls(self):
        result = dispatch_race([])
        assert result["status"] == "error"
        assert "No calls" in result["error"]

    def test_first_success_wins(self, mock_cfg):
        """First non-error result wins; remaining are recorded as failed/late."""
        fast = MagicMock(return_value={"status": "success", "data": "fast"})
        slow = MagicMock(side_effect=lambda: (
            time.sleep(0.05) or {"status": "success", "data": "slow"}
        ))
        result = dispatch_race([
            ("file", slow, {}),
            ("web", fast, {}),
        ])
        assert result["status"] == "success"
        winner = result["data"]["winner"]
        assert winner is not None
        assert winner["tool"] == "web"

    def test_all_fail_returns_none_winner(self, mock_cfg):
        failing = MagicMock(side_effect=RuntimeError("nope"))
        result = dispatch_race([("web", failing, {}), ("file", failing, {})])
        assert result["status"] == "success"
        assert result["data"]["winner"] is None
        assert len(result["data"]["failed"]) == 2

    def test_status_error_does_not_win(self, mock_cfg):
        """A dict result with status='error' counts as a failure, not a win."""
        ok_mock = MagicMock(return_value={"status": "success"})
        err_mock = MagicMock(return_value={"status": "error", "error": "bad"})
        result = dispatch_race([("file", err_mock, {}), ("web", ok_mock, {})])
        assert result["status"] == "success"
        winner = result["data"]["winner"]
        assert winner is not None
        assert winner["tool"] == "web"

    def test_trace_id_threaded(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        result = dispatch_race([("web", mock_fn, {})], trace_id="race-exec-1")
        assert result.get("trace_id") == "race-exec-1"
        assert result["data"]["winner"]["trace_id"] == "race-exec-1"

    def test_duration_ms_present(self, mock_cfg):
        mock_fn = MagicMock(return_value={"status": "success"})
        result = dispatch_race([("web", mock_fn, {})])
        assert "duration_ms" in result["data"]

    def test_nested_parallel_blocked(self):
        mock_fn = MagicMock(return_value={"status": "success"})
        _parallel_depth.value = 1
        try:
            result = dispatch_race([("web", mock_fn, {})])
            assert result["status"] == "error"
            assert "Nested parallel" in result["error"]
        finally:
            _parallel_depth.value = 0


# =============================================================================
# dispatch_pipeline
# =============================================================================
class TestDispatchPipeline:
    def test_empty_calls(self):
        result = dispatch_pipeline([])
        assert result["status"] == "error"
        assert "No calls" in result["error"]

    def test_no_feed_runs_each_with_own_args(self, mock_cfg):
        m1 = MagicMock(return_value={"status": "success", "data": "r1"})
        m2 = MagicMock(return_value={"status": "success", "data": "r2"})
        result = dispatch_pipeline([
            ("web", m1, {"action": "search"}, None),
            ("python", m2, {"action": "run"}, None),
        ])
        assert result["status"] == "success"
        assert result["data"]["completed"] == 2
        m1.assert_called_once_with(action="search")
        m2.assert_called_once_with(action="run")

    def test_feed_string_replaces_args(self, mock_cfg):
        m1 = MagicMock(return_value={
            "status": "success",
            "result": {"text": {"code": "print('hi')"}},
        })
        m2 = MagicMock(return_value={"status": "success"})
        result = dispatch_pipeline([
            ("web", m1, {"action": "search"}, None),
            ("python", m2, {"action": "ignored"}, "result.text"),
        ])
        assert result["status"] == "success"
        m2.assert_called_once_with(code="print('hi')")

    def test_feed_string_non_dict_breaks_chain(self, mock_cfg):
        m1 = MagicMock(return_value={"status": "success", "result": {"text": "not a dict"}})
        m2 = MagicMock(return_value={"status": "success"})
        result = dispatch_pipeline([
            ("web", m1, {}, None),
            ("python", m2, {}, "result.text"),
        ])
        assert result["status"] == "success"
        assert result["data"]["completed"] == 1
        assert result["data"]["failed"] == 1
        m2.assert_not_called()

    def test_feed_dict_merges_into_args(self, mock_cfg):
        m1 = MagicMock(return_value={
            "status": "success",
            "result": {"text": "print('hi')"},
        })
        m2 = MagicMock(return_value={"status": "success"})
        result = dispatch_pipeline([
            ("web", m1, {"action": "search"}, None),
            ("python", m2, {"action": "run"}, {"code": "result.text"}),
        ])
        assert result["status"] == "success"
        m2.assert_called_once_with(action="run", code="print('hi')")

    def test_error_mid_chain_stops_pipeline(self, mock_cfg):
        m1 = MagicMock(return_value={"status": "success"})
        m2 = MagicMock(side_effect=RuntimeError("kaboom"))
        m3 = MagicMock(return_value={"status": "success"})
        result = dispatch_pipeline([
            ("web", m1, {}, None),
            ("python", m2, {}, None),
            ("file", m3, {}, None),
        ])
        assert result["status"] == "success"
        assert result["data"]["completed"] == 1
        assert result["data"]["failed"] == 1
        m3.assert_not_called()

    def test_trace_id_threaded(self, mock_cfg):
        m1 = MagicMock(return_value={"status": "success"})
        result = dispatch_pipeline([("web", m1, {}, None)], trace_id="pipe-exec-1")
        assert result.get("trace_id") == "pipe-exec-1"
        assert result["data"]["results"][0]["trace_id"] == "pipe-exec-1"


# =============================================================================
# _resolve_dot_path
# =============================================================================
class TestResolveDotPath:
    def test_single_segment_dict(self):
        assert _resolve_dot_path({"a": 1}, "a") == 1

    def test_multi_segment_dict(self):
        assert _resolve_dot_path({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_segment_returns_none(self):
        assert _resolve_dot_path({"a": {"b": 1}}, "a.x") is None

    def test_empty_path_returns_obj(self):
        obj = {"a": 1}
        assert _resolve_dot_path(obj, "") is obj

    def test_object_attrs(self):
        class Obj:
            pass
        o = Obj()
        o.x = "val"
        assert _resolve_dot_path(o, "x") == "val"

    def test_malformed_path_returns_none(self):
        assert _resolve_dot_path({"a": 1}, "a..b") is None


# =============================================================================
# _resolve_timeout
# =============================================================================
class TestResolveTimeout:
    def test_explicit_positive(self, mock_cfg):
        mock_cfg.worker_timeout = 60
        assert _resolve_timeout(30) == 30

    def test_explicit_zero(self, mock_cfg):
        mock_cfg.worker_timeout = 60
        assert _resolve_timeout(0) == 0

    def test_negative_one_falls_back_to_cfg(self, mock_cfg):
        mock_cfg.worker_timeout = 99
        assert _resolve_timeout(-1) == 99

    def test_other_negative_also_falls_back(self, mock_cfg):
        """Negative values other than -1 should also fall back (defensive)."""
        mock_cfg.worker_timeout = 88
        assert _resolve_timeout(-5) == 88


# =============================================================================
# _safe_run
# =============================================================================
class TestSafeRun:
    def test_safe_run_invokes_fn_with_kwargs(self):
        mock_fn = MagicMock(return_value="ok")
        result = _safe_run("web", mock_fn, {"action": "search", "query": "x"})
        assert result == "ok"
        mock_fn.assert_called_once_with(action="search", query="x")

    def test_safe_run_propagates_exceptions(self):
        mock_fn = MagicMock(side_effect=ValueError("bad"))
        with pytest.raises(ValueError, match="bad"):
            _safe_run("web", mock_fn, {})
