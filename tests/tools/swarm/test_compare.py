"""Tests for swarm compare action."""
from __future__ import annotations
from tools.swarm import swarm


class TestCompare:
    """compare: all providers answer, responses returned side-by-side."""

    def test_compare_success(self, mock_llm_registry):
        """Should return all responses without synthesis."""
        result = swarm(action="compare", question="Explain RAFT in 3 sentences.")
        assert result["status"] == "success"
        data = result["data"]
        assert data["provider_count"] == 3
        assert data["successful_count"] == 3
        assert len(data["responses"]) == 3
        # compare does NOT have a synthesis field
        assert "synthesis" not in data

    def test_compare_missing_question(self, mock_llm_registry):
        """Should fail if question is empty."""
        result = swarm(action="compare")
        assert result["status"] == "error"
        assert "question is required" in result["error"]

    def test_compare_no_providers(self, mock_llm_empty_registry):
        """Should fail when no cloud providers configured."""
        result = swarm(action="compare", question="test")
        assert result["status"] == "error"
        assert "No cloud providers" in result["error"]

    def test_compare_all_providers_fail(self, mock_failing_providers):
        """Should fail when all providers return errors."""
        result = swarm(action="compare", question="test")
        assert result["status"] == "error"
        assert "All providers failed" in result["error"]

    def test_compare_provider_filter(self, mock_llm_registry):
        """Should only call filtered providers."""
        result = swarm(action="compare", question="test", providers="claude")
        assert result["status"] == "success"
        assert result["data"]["provider_count"] == 1
