"""Tests for swarm consensus action."""
from __future__ import annotations
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
