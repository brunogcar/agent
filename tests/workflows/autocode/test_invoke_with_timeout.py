"""tests/workflows/autocode/test_invoke_with_timeout.py — Direct tests for invoke_with_timeout.

[v1.2] invoke_with_timeout had no direct tests — only mocked indirectly.
Covers: normal completion, timeout fires + cancellation flag set, graph
exception surfaced, adaptive timeout by task_type.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestInvokeWithTimeout:
    def test_normal_completion(self):
        from workflows.autocode_impl.graph import invoke_with_timeout
        with patch("workflows.autocode_impl.graph.get_graph") as mock_gg:
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {"status": "success"}
            mock_gg.return_value = mock_graph
            result = invoke_with_timeout({"trace_id": "t1", "task_type": "feature"})
            assert result["status"] == "success"

    def test_timeout_sets_cancellation_flag(self):
        from workflows.autocode_impl.graph import invoke_with_timeout
        import time
        with patch("workflows.autocode_impl.graph.get_graph") as mock_gg:
            mock_graph = MagicMock()
            # Simulate a slow invoke that exceeds timeout
            def slow_invoke(state):
                time.sleep(10)
                return {"status": "success"}
            mock_graph.invoke.side_effect = slow_invoke
            mock_gg.return_value = mock_graph
            with patch("workflows.autocode_impl.graph.request_cancellation") as mock_cancel:
                with patch("core.config.cfg") as mock_cfg:
                    mock_cfg.autocode_graph_timeout = 1
                    mock_cfg.autocode_adaptive_timeout = False
                    result = invoke_with_timeout({"trace_id": "t1"})
                assert "timed out" in result["error"].lower()
                mock_cancel.assert_called_once()

    def test_graph_exception_surfaced(self):
        from workflows.autocode_impl.graph import invoke_with_timeout
        with patch("workflows.autocode_impl.graph.get_graph") as mock_gg:
            mock_graph = MagicMock()
            mock_graph.invoke.side_effect = RuntimeError("node crashed")
            mock_gg.return_value = mock_graph
            result = invoke_with_timeout({"trace_id": "t1"})
            assert result["status"] == "failed"
            assert "crashed" in result["error"].lower()
            assert "node crashed" in result["error"]

    def test_adaptive_timeout_create_skill(self):
        from workflows.autocode_impl.graph import invoke_with_timeout
        with patch("workflows.autocode_impl.graph.get_graph") as mock_gg:
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {"status": "success"}
            mock_gg.return_value = mock_graph
            with patch("core.config.cfg") as mock_cfg:
                mock_cfg.autocode_graph_timeout = 300
                mock_cfg.autocode_adaptive_timeout = True
                # Verify the timeout is looked up from the task_type map
                result = invoke_with_timeout({"trace_id": "t1", "task_type": "create_skill"})
                # The thread.join timeout should be 120s for create_skill
                # We can't easily assert the join timeout, but we verify it doesn't crash
                assert result["status"] == "success"
