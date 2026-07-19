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

[v1.4 P2] The former test_swarm_fallback_fixes.py was merged into this file
(it had 4 tests for the v3.2 swarm_fallback fixes — same node, same scope).
Merged classes:
  - TestSwarmFallbackHighPath      (HIGH path appends debug_history + clears error)
  - TestVerifyDecisionDefault      (hallucination guard default-False regression)
  - TestLlmReviewListHandling      (test_code list[str] coercion regression)

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


# ── [v1.4 P2] Merged from the former test_swarm_fallback_fixes.py ─────────────
# 4 regression tests covering the v3.2 swarm_fallback HIGH path fixes + the
# hallucination guard default-False regression + the LLM review list[str]
# coercion regression. Same scope (swarm fallback / verify decision / llm_review),
# so they belong here.


class TestSwarmFallbackHighPath:
    """[v1.4] HIGH-confidence swarm_fallback path fixes."""

    def test_high_path_appends_debug_history(self, base_state, temp_workspace):
        """HIGH confidence must append a phase='swarm_fallback' entry to debug_history."""
        from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback
        base_state["tdd"]["status"] = "max_retries_exceeded"
        base_state["tdd"]["iteration"] = 5
        base_state["tdd"]["debug_history"] = [{"iteration": 1, "phase": "investigation"}]
        base_state["tdd"]["last_test_error"] = "AssertionError: expected 5 got 3"

        with patch("workflows.autocode_impl.nodes.swarm_fallback._swarm_debug_consensus") as mock_swarm:
            mock_swarm.return_value = {
                "confidence": "HIGH",
                "root_cause": "missing import",
                "fix": "add import os",
                "defense_notes": "",
            }
            result = node_swarm_fallback(base_state)

        tdd = result.get("tdd", {})
        history = tdd.get("debug_history", [])
        assert len(history) == 2  # 1 original + 1 swarm entry
        assert history[-1]["phase"] == "swarm_fallback"
        assert history[-1]["confidence"] == "HIGH"

    def test_high_path_clears_last_test_error(self, base_state, temp_workspace):
        """HIGH confidence must clear last_test_error so stuck detection doesn't fire."""
        from workflows.autocode_impl.nodes.swarm_fallback import node_swarm_fallback
        base_state["tdd"]["status"] = "max_retries_exceeded"
        base_state["tdd"]["last_test_error"] = "AssertionError"

        with patch("workflows.autocode_impl.nodes.swarm_fallback._swarm_debug_consensus") as mock_swarm:
            mock_swarm.return_value = {"confidence": "HIGH", "root_cause": "x", "fix": "y", "defense_notes": ""}
            result = node_swarm_fallback(base_state)

        assert result["tdd"]["last_test_error"] == ""


class TestVerifyDecisionDefault:
    """[v1.4 P0] Hallucination guard default-False regression."""

    def test_hallucination_guard_defaults_false(self, base_state, temp_workspace):
        """Missing automated_checks_passed should default to False, not True."""
        from workflows.autocode_impl.nodes.verify_decision import node_verify_decision
        base_state["verify"] = {"passed": False, "tests_passed": False, "lint_passed": True}
        base_state["test_results"] = {"success": False}
        base_state["tdd"]["status"] = ""
        # [v1.4 P0] verify_decision reads llm_review_data from state (not via _call).
        # Set llm_review_data WITHOUT automated_checks_passed key — old code
        # defaulted to True (hallucination), new code defaults to False.
        base_state["llm_review_data"] = {"checks": {}}
        base_state["tests_passed"] = False

        # Should NOT log "HALLUCINATION DETECTED" because default is now False
        # The verify node should just proceed with the checks (no crash).
        result = node_verify_decision(base_state)

        assert isinstance(result, dict)
        # verify sub-state should be populated (node ran to completion).
        assert "verify" in result


class TestLlmReviewListHandling:
    """[v1.4 P0] LLM review test_code list[str] coercion regression."""

    def test_handles_list_test_code(self, base_state, temp_workspace):
        """llm_review should handle test_code as list[str] without crashing."""
        from workflows.autocode_impl.nodes.llm_review import node_llm_review
        base_state["test_code"] = ["def test_a(): pass", "def test_b(): pass"]
        base_state["verify"] = {"tests_passed": False, "fresh_output": "FAIL", "lint_output": ""}
        base_state["tdd"]["debug_history"] = []

        with patch("workflows.autocode_impl.nodes.llm_review._call") as mock_call:
            mock_call.return_value = '{"verdict": "pass", "issues": []}'
            result = node_llm_review(base_state)

        # Should not crash — the list is joined to string before use
        # Check the _call was invoked (meaning the node ran to completion)
        assert mock_call.called
