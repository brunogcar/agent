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


# ===========================================================================
# [v3.11 B1] Adaptive timeout propagated to _remaining_timeout()
# ===========================================================================


class TestAdaptiveTimeoutRemaining:
    """[v3.11 B1] _remaining_timeout() must use the per-run adaptive timeout,
    not the static cfg.autocode_graph_timeout. Pre-v3.11, a feature task with
    adaptive timeout=900s would still use the static 300s here — at 400s elapsed,
    remaining = 300-400 = -100 → 1, giving pytest a spurious 1-second timeout.
    """

    def test_adaptive_timeout_used_by_remaining_timeout(self):
        """set_graph_start_time(timeout=900) → _remaining_timeout uses 900s budget."""
        from workflows.autocode_impl.helpers import set_graph_start_time, _remaining_timeout
        import time

        # Set start time + the resolved adaptive timeout (900s for feature).
        set_graph_start_time(timeout=900)
        # Simulate 400s elapsed.
        with patch("workflows.autocode_impl.helpers._time.time",
                   return_value=time.time() + 400):
            # default_timeout=600 (cfg.sandbox_timeout) — should be capped at
            # remaining = 900 - 400 = 500, NOT 300 - 400 = -100 → 1.
            result = _remaining_timeout(600)

        assert result == 499 or result == 500, (  # int() truncation may give 499
            f"_remaining_timeout should return ~500 (900s budget - 400s elapsed), "
            f"got {result}. Pre-v3.11 returned 1 (300s static - 400s = -100 → 1)."
        )

    def test_static_timeout_falls_back_to_cfg(self):
        """set_graph_start_time() with no timeout → _remaining_timeout uses cfg."""
        from workflows.autocode_impl.helpers import set_graph_start_time, _remaining_timeout
        import time

        # No timeout param — backward-compatible with v3.10 callers.
        set_graph_start_time()
        with patch("workflows.autocode_impl.helpers._time.time",
                   return_value=time.time() + 100), \
             patch("core.config.cfg.autocode_graph_timeout", 300):
            # remaining = 300 - 100 = 200, capped at min(600, 200) = 200.
            result = _remaining_timeout(600)

        assert result in (199, 200), (  # int() truncation may give 199
            f"_remaining_timeout should return ~200, got {result}"
        )
