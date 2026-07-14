"""[v1.1 #17] Smoke tests for swarm <-> autocode debug loop integration.

Verifies that AUTOCODE_SWARM_DEBUG=1 actually triggers the swarm path
in debug.py, and that AUTOCODE_SWARM_DEBUG_FALLBACK=1 triggers
swarm_fallback.py. These were silently broken before v1.0.2.

Scope:
  - TestSwarmDebugIntegration: AUTOCODE_SWARM_DEBUG=1 <-> debug.py
    (the swarm-inside-loop path; swarm runs on every debug iteration).
  - TestSwarmFallbackIntegration: AUTOCODE_SWARM_DEBUG_FALLBACK=1 <->
    swarm_fallback.py (the swarm-on-exhaustion path; runs once after
    the debug loop gives up at max_retries_exceeded).

These tests do NOT make real provider calls — _swarm_debug_consensus is
mocked on the import path used by each node module.
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest


class TestSwarmDebugIntegration:
    """[v1.1 #17] Verify AUTOCODE_SWARM_DEBUG=1 triggers swarm path."""

    def test_swarm_debug_called_when_enabled(self, mocker):
        """When AUTOCODE_SWARM_DEBUG=1, debug.py calls _swarm_debug_consensus."""
        from workflows.autocode_impl.state import _default_state
        from workflows.autocode_impl.nodes.debug import node_systematic_debug

        mocker.patch("core.config.cfg.autocode_swarm_debug", True)
        mock_swarm = mocker.patch("workflows.autocode_impl.nodes.debug._swarm_debug_consensus")
        mock_swarm.return_value = {
            "root_cause": "off by one",
            "fix": "change < to <=",
            "defense_notes": "add bounds check",
            "confidence": "HIGH",
            "agreement": "unanimous",
            "providers": 3,
        }

        state = _default_state(task="fix bug")
        state["trace_id"] = "t1"
        state["tdd"]["status"] = "failed"
        state["tdd"]["iteration"] = 1
        state["tdd"]["error"] = "AssertionError"
        state["test_results"] = {"success": False, "stdout": "", "stderr": "AssertionError"}
        state["max_retries"] = 3

        result = node_systematic_debug(state)
        mock_swarm.assert_called_once()
        assert result.get("debug", {}).get("swarm_verdict") is not None

    def test_swarm_debug_skipped_when_disabled(self, mocker):
        """When AUTOCODE_SWARM_DEBUG=0, debug.py does NOT call swarm."""
        from workflows.autocode_impl.state import _default_state
        from workflows.autocode_impl.nodes.debug import node_systematic_debug

        mocker.patch("core.config.cfg.autocode_swarm_debug", False)
        mock_swarm = mocker.patch("workflows.autocode_impl.nodes.debug._swarm_debug_consensus")
        mock_call = mocker.patch("workflows.autocode_impl.nodes.debug._call")
        mock_call.return_value = '{"phase": "fix", "root_cause": "x", "fix": "y", "defense_notes": ""}'

        state = _default_state(task="fix bug")
        state["trace_id"] = "t1"
        state["tdd"]["status"] = "failed"
        state["tdd"]["iteration"] = 1
        state["tdd"]["error"] = "AssertionError"
        state["test_results"] = {"success": False, "stdout": "", "stderr": "AssertionError"}
        state["max_retries"] = 3

        result = node_systematic_debug(state)
        mock_swarm.assert_not_called()


class TestSwarmFallbackIntegration:
    """[v1.1 #17] Verify AUTOCODE_SWARM_DEBUG_FALLBACK=1 triggers swarm_fallback."""

    def test_swarm_fallback_routes_to_debug_on_high(self, mocker):
        """When swarm returns HIGH confidence, swarm_fallback resets tdd_status."""
        from workflows.autocode_impl.state import _default_state
        from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback

        mocker.patch("workflows.autocode_impl.nodes.swarm_fallback._swarm_debug_consensus")
        from workflows.autocode_impl.nodes.swarm_fallback import _swarm_debug_consensus
        _swarm_debug_consensus.return_value = {
            "root_cause": "missing import",
            "fix": "import os",
            "defense_notes": "check imports",
            "confidence": "HIGH",
            "agreement": "unanimous",
            "providers": 3,
        }

        state = _default_state(task="fix bug")
        state["trace_id"] = "t1"
        state["tdd"]["status"] = "max_retries_exceeded"
        state["tdd"]["error"] = "ImportError"
        state["tdd"]["debug_history"] = [{"iteration": 1, "root_cause": "x", "fix": "y"}]

        result = node_swarm_fallback(state)
        # HIGH confidence -> tdd_status reset to "" (allows one more debug cycle)
        assert result.get("tdd", {}).get("status") == ""
        assert result.get("debug", {}).get("swarm_verdict") is not None
        assert result.get("status") != "failed"  # NOT failed -- will retry

    def test_swarm_fallback_fails_on_low(self, mocker):
        """When swarm returns LOW confidence, swarm_fallback sets status=failed."""
        from workflows.autocode_impl.state import _default_state
        from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback

        mocker.patch("workflows.autocode_impl.nodes.swarm_fallback._swarm_debug_consensus")
        from workflows.autocode_impl.nodes.swarm_fallback import _swarm_debug_consensus
        _swarm_debug_consensus.return_value = {
            "root_cause": "unknown",
            "fix": "",
            "defense_notes": "",
            "confidence": "LOW",
            "agreement": "disagreement",
            "providers": 3,
        }

        state = _default_state(task="fix bug")
        state["trace_id"] = "t1"
        state["tdd"]["status"] = "max_retries_exceeded"
        state["tdd"]["error"] = "UnknownError"

        result = node_swarm_fallback(state)
        assert result.get("status") == "failed"
        assert result.get("debug", {}).get("swarm_verdict") is not None

    def test_swarm_fallback_fails_when_swarm_unavailable(self, mocker):
        """When swarm returns None (unavailable), swarm_fallback sets status=failed."""
        from workflows.autocode_impl.state import _default_state
        from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback

        mocker.patch("workflows.autocode_impl.nodes.swarm_fallback._swarm_debug_consensus", return_value=None)

        state = _default_state(task="fix bug")
        state["trace_id"] = "t1"
        state["tdd"]["status"] = "max_retries_exceeded"
        state["tdd"]["error"] = "UnknownError"

        result = node_swarm_fallback(state)
        assert result.get("status") == "failed"
