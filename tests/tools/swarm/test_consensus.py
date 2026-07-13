"""Tests for swarm consensus action.

v1.0.2 (cross-LLM): Added tests for synthesis-failure surfacing (P1-5),
whitespace-only response filtering (P1-3), and the new synthesis_failed /
synthesis_error fields.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch
from tools.swarm import swarm


class TestConsensus:
    """consensus: all providers answer, planner synthesizes."""

    def test_consensus_success(self, mock_llm_registry):
        """Should return responses from all providers + synthesis."""
        result = swarm(action="consensus", question="How to handle errors in Python?")
        assert result["status"] == "success"
        data = result["data"]
        assert data["provider_count"] == 3
        assert data["successful_count"] == 3
        assert len(data["responses"]) == 3
        assert data["synthesis"] == "Synthesized answer combining all responses."
        # v1.0.2 (P1-5): synthesis_failed flag should be present and False on success
        assert data["synthesis_failed"] is False
        assert data["synthesis_error"] == ""

    def test_consensus_missing_question(self, mock_llm_registry):
        """Should fail if question is empty."""
        result = swarm(action="consensus")
        assert result["status"] == "error"
        assert "question is required" in result["error"]

    def test_consensus_no_providers(self, mock_llm_empty_registry):
        """Should fail when no cloud providers configured."""
        result = swarm(action="consensus", question="test")
        assert result["status"] == "error"
        assert "No cloud providers" in result["error"]

    def test_consensus_all_providers_fail(self, mock_failing_providers):
        """Should fail when all providers return errors."""
        result = swarm(action="consensus", question="test")
        assert result["status"] == "error"
        assert "All providers failed" in result["error"]

    def test_consensus_provider_filter(self, mock_llm_registry):
        """Should only call filtered providers."""
        result = swarm(action="consensus", question="test", providers="openai,deepseek")
        assert result["status"] == "success"
        assert result["data"]["provider_count"] == 2

    def test_consensus_responses_have_metadata(self, mock_llm_registry):
        """Each response should have provider, model, text, latency, tokens."""
        result = swarm(action="consensus", question="test")
        assert result["status"] == "success"
        for r in result["data"]["responses"]:
            assert "provider" in r
            assert "model" in r
            assert "text" in r
            assert "latency" in r
            assert "tokens" in r
            assert "error" in r

    def test_consensus_synthesis_failure_surfaced(self, mock_providers):
        """v1.0.2 (P1-5 cross-LLM): If planner synthesis fails, the action
        still succeeds (responses are valuable) but surfaces the failure via
        synthesis_failed=True + synthesis_error. v1.0.1 silently returned
        synthesis="" with no failure indicator.
        """
        import os
        # Build a registry where llm.complete returns a failed synthesis
        with patch("core.llm.llm") as mock_llm:
            mock_llm._registry._providers = {
                "lmstudio": MagicMock(),
                **mock_providers,
            }
            # Synthesis fails
            failed_synthesis = MagicMock()
            failed_synthesis.ok = False
            failed_synthesis.text = ""
            failed_synthesis.error = "planner timeout"
            mock_llm.complete.return_value = failed_synthesis

            original_getenv = os.getenv
            def _mock_getenv(key, default=""):
                if key == "OPENAI_BASE_MODEL":
                    return "gpt-4o-mini"
                elif key == "DEEPSEEK_BASE_MODEL":
                    return "deepseek-chat"
                elif key == "CLAUDE_BASE_MODEL":
                    return "claude-3-5-haiku-20241022"
                return original_getenv(key, default)

            with patch("os.getenv", side_effect=_mock_getenv):
                result = swarm(action="consensus", question="test")

        assert result["status"] == "success"  # responses still present
        data = result["data"]
        assert data["synthesis"] == ""
        assert data["synthesis_failed"] is True
        assert "planner timeout" in data["synthesis_error"]
        # successful_count reflects providers, not synthesis
        assert data["successful_count"] == 3

    def test_consensus_whitespace_only_responses_filtered(self, make_vote_providers):
        """v1.0.2 (P1-3 cross-LLM): Whitespace-only provider responses must
        not count as successful. v1.0.1 bug: "   " was truthy, passed the
        filter, then got included in the synthesis prompt as empty text.
        """
        llm = make_vote_providers({
            "openai": "   ",       # whitespace only — should be filtered out
            "claude": "real answer",
        })
        next(llm)
        result = swarm(action="consensus", question="test")
        assert result["status"] == "success"
        data = result["data"]
        # Only claude should count as successful
        assert data["successful_count"] == 1
        assert data["provider_count"] == 2  # both were attempted
