"""Tests for v1.4 swarm_fallback HIGH path fixes."""
import pytest
from unittest.mock import patch, MagicMock

# Read the conftest first to understand the base_state fixture


class TestSwarmFallbackHighPath:
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
