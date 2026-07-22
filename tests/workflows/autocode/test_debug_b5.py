"""tests/workflows/autocode/test_debug_b5.py — [v3.11 B5] debug path cancellation checks.

The 3 debug paths (swarm, parallel-subagent, single-subagent) bypassed the
v3.6 cancellation-aware wrappers. Once the graph timed out + the caller got a
timeout response, in-flight swarm()/agent() calls kept running in the
background, not bounded by the graph deadline. The CHANGELOG's "≤1s past graph
deadline" claim was overstated for SWARM/SUBAGENT/PARALLEL_SUBAGENT modes.

v3.11 B5 adds is_cancellation_requested() pre-checks to all 3 paths.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestDebugSwarmCancellation:
    """[v3.11 B5] Swarm path checks cancellation before dispatching."""

    def test_swarm_skipped_when_cancelled(self, base_state):
        """When is_cancellation_requested() returns True, the swarm path
        skips _swarm_debug_consensus + falls through to single-LLM."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug
        from workflows.autocode_impl.constants import DEBUG_SYSTEM

        state = dict(base_state)
        state["tdd"]["test_error"] = "AssertionError: expected 5 got 4"
        state["tdd"]["test_file"] = "test_foo.py"
        state["tdd"]["debug_history"] = []
        state["tdd"]["max_retries"] = 3
        state["tdd"]["retry_count"] = 0
        state["impact"] = {"blast_radius": []}

        with patch("core.config.cfg.autocode_swarm_debug", True), \
             patch("workflows.autocode_impl.nodes.debug.is_cancellation_requested",
                   return_value=True), \
             patch("workflows.autocode_impl.vcs_ops._swarm_debug_consensus") as mock_swarm, \
             patch("workflows.autocode_impl.nodes.debug._call",
                   return_value='{"phase": "fix", "root_cause": "x", "fix": "y", "defense_notes": ""}'):
            result = node_systematic_debug(state)
            # swarm was NOT called (cancelled).
            mock_swarm.assert_not_called()
            # Fell through to single-LLM _call (which returned the mock JSON).
            assert "tdd" in result


class TestDebugParallelSubagentCancellation:
    """[v3.11 B5] Parallel-subagent path checks cancellation before dispatching."""

    def test_parallel_subagent_skipped_when_cancelled(self, base_state):
        """When is_cancellation_requested() returns True, the parallel-subagent
        path skips _parallel_subagent_debug + falls through to single-LLM."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug

        state = dict(base_state)
        state["tdd"]["test_error"] = "AssertionError: expected 5 got 4"
        state["tdd"]["test_file"] = "test_foo.py"
        state["tdd"]["debug_history"] = []
        state["tdd"]["max_retries"] = 3
        state["tdd"]["retry_count"] = 0
        state["impact"] = {"blast_radius": []}

        with patch("core.config.cfg.autocode_parallel_subagent_debug", True), \
             patch("workflows.autocode_impl.nodes.debug.is_cancellation_requested",
                   return_value=True), \
             patch("workflows.autocode_impl.nodes.debug._parallel_subagent_debug") as mock_parallel, \
             patch("workflows.autocode_impl.nodes.debug._call",
                   return_value='{"phase": "fix", "root_cause": "x", "fix": "y", "defense_notes": ""}'):
            result = node_systematic_debug(state)
            # parallel-subagent was NOT called (cancelled).
            mock_parallel.assert_not_called()
            # Fell through to single-LLM _call.
            assert "tdd" in result


class TestDebugSingleSubagentCancellation:
    """[v3.11 B5] Single-subagent path checks cancellation before dispatching."""

    def test_single_subagent_skipped_when_cancelled(self, base_state):
        """When is_cancellation_requested() returns True, the single-subagent
        path skips the agent() call + falls through to single-LLM."""
        from workflows.autocode_impl.nodes.debug import node_systematic_debug

        state = dict(base_state)
        state["tdd"]["test_error"] = "AssertionError: expected 5 got 4"
        state["tdd"]["test_file"] = "test_foo.py"
        state["tdd"]["debug_history"] = []
        state["tdd"]["max_retries"] = 3
        state["tdd"]["retry_count"] = 0
        state["impact"] = {"blast_radius": []}

        with patch("core.config.cfg.autocode_subagent_debug", True), \
             patch("workflows.autocode_impl.nodes.debug.is_cancellation_requested",
                   return_value=True), \
             patch("tools.agent.agent") as mock_agent, \
             patch("workflows.autocode_impl.nodes.debug._call",
                   return_value='{"phase": "fix", "root_cause": "x", "fix": "y", "defense_notes": ""}'):
            result = node_systematic_debug(state)
            # agent() was NOT called (cancelled).
            mock_agent.assert_not_called()
            # Fell through to single-LLM _call.
            assert "tdd" in result
