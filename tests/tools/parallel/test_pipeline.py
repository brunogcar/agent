"""Tests for the 'pipeline' action of the parallel meta-tool.

Covers:
  - Sequential execution (tasks run in order, not parallel)
  - feed=None (no feeding — each task uses own args)
  - feed=str (dot-path resolves to dict, replaces args)
  - feed=dict (merges fed values into base args)
  - Error mid-chain stops the pipeline
  - trace_id threading
  - Pipeline does NOT enforce PARALLEL_SAFE (sequential)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

from tools.parallel import parallel
from tools.parallel_ops.tool_map import _TOOL_MAP


class TestPipelineValidation:
    def test_empty_tasks(self):
        result = parallel(action="pipeline", tasks=[])
        assert result["status"] == "error"
        assert "No tasks provided" in result["error"]

    def test_unknown_tool(self):
        result = parallel(action="pipeline", tasks=[{"name": "nonexistent", "args": {}}])
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_invalid_feed_type(self):
        mock_fn = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_fn}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {}, "feed": 123},
            ])
            assert result["status"] == "error"
            assert "feed must be" in result["error"]


class TestPipelineExecution:
    def test_no_feed_uses_own_args(self, mock_cfg):
        """When feed is omitted, each task uses its own args as-is."""
        mock_web = MagicMock(return_value={"status": "success", "data": "r1"})
        mock_py = MagicMock(return_value={"status": "success", "data": "r2"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {"action": "search", "query": "x"}},
                {"name": "python", "args": {"action": "run", "code": "1+1"}},
            ])
            assert result["status"] == "success"
            assert result["data"]["completed"] == 2
            mock_web.assert_called_once_with(action="search", query="x")
            mock_py.assert_called_once_with(action="run", code="1+1")

    def test_feed_string_replaces_args(self, mock_cfg):
        """feed='result.text' on a dict-typed resolved value replaces args entirely."""
        # First task returns {"result": {"text": {"code": "print('hi')"}}}
        # (resolved dict). Second task's args are replaced by that dict.
        mock_web = MagicMock(return_value={
            "status": "success",
            "result": {"text": {"code": "print('hi')"}},
        })
        mock_py = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {"action": "search", "query": "x"}},
                {"name": "python", "args": {"action": "ignored"}, "feed": "result.text"},
            ])
            assert result["status"] == "success"
            # Second call should have received the fed dict (NOT the original args).
            mock_py.assert_called_once_with(code="print('hi')")

    def test_feed_string_non_dict_breaks_chain(self, mock_cfg):
        """If feed=str resolves to a non-dict, pipeline breaks with an error."""
        mock_web = MagicMock(return_value={"status": "success", "result": {"text": "not a dict"}})
        mock_py = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {}},
                {"name": "python", "args": {}, "feed": "result.text"},
            ])
            assert result["status"] == "success"  # envelope still success
            assert result["data"]["completed"] == 1  # only first ran
            assert result["data"]["failed"] == 1
            assert "did not resolve to a dict" in result["data"]["errors"][0]["error"]
            mock_py.assert_not_called()

    def test_feed_dict_merges_into_args(self, mock_cfg):
        """feed={"code": "result.text"} merges 'code' into the base args."""
        mock_web = MagicMock(return_value={
            "status": "success",
            "result": {"text": "print('hi')"},
        })
        mock_py = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {"action": "search", "query": "x"}},
                {"name": "python", "args": {"action": "run"}, "feed": {"code": "result.text"}},
            ])
            assert result["status"] == "success"
            mock_py.assert_called_once_with(action="run", code="print('hi')")

    def test_feed_dict_missing_path_yields_none(self, mock_cfg):
        """If a feed dot-path is missing, the arg is set to None (not fatal)."""
        mock_web = MagicMock(return_value={"status": "success", "result": {}})  # no 'text' key
        mock_py = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {}},
                {"name": "python", "args": {"action": "run"}, "feed": {"code": "result.text"}},
            ])
            assert result["status"] == "success"
            mock_py.assert_called_once_with(action="run", code=None)

    def test_error_mid_chain_stops_pipeline(self, mock_cfg):
        """If task[1] raises, task[2] is never attempted."""
        mock_web = MagicMock(return_value={"status": "success", "data": "r1"})
        mock_py = MagicMock(side_effect=RuntimeError("kaboom"))
        mock_file = MagicMock(return_value={"status": "success"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py, "file": mock_file}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "web", "args": {}},
                {"name": "python", "args": {}},
                {"name": "file", "args": {}},
            ])
            assert result["status"] == "success"
            assert result["data"]["completed"] == 1
            assert result["data"]["failed"] == 1
            assert "kaboom" in result["data"]["errors"][0]["error"]
            mock_file.assert_not_called()

    def test_trace_id_threaded(self, mock_cfg):
        mock_web = MagicMock(return_value={"status": "success", "data": "r1"})
        mock_py = MagicMock(return_value={"status": "success", "data": "r2"})
        with patch.dict(_TOOL_MAP, {"web": mock_web, "python": mock_py}, clear=False):
            result = parallel(
                action="pipeline",
                tasks=[
                    {"name": "web", "args": {}},
                    {"name": "python", "args": {}, "feed": {"code": "result.text"}},
                ],
                trace_id="pipe-trace-1",
            )
            assert result.get("trace_id") == "pipe-trace-1"
            assert result["data"]["results"][0]["trace_id"] == "pipe-trace-1"

    def test_pipeline_allows_unsafe_tools(self, mock_cfg):
        """Pipeline is sequential — PARALLEL_SAFE does not apply."""
        # 'unsafe_tool' is NOT in PARALLEL_SAFE but pipeline should still run it.
        mock_fn = MagicMock(return_value={"status": "success", "data": "ok"})
        with patch.dict(_TOOL_MAP, {"unsafe_tool": mock_fn}, clear=False):
            result = parallel(action="pipeline", tasks=[
                {"name": "unsafe_tool", "args": {}},
            ])
            assert result["status"] == "success"
            assert result["data"]["completed"] == 1
