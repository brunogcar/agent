"""Tests for swarm race action."""
from __future__ import annotations
from tools.swarm import swarm


class TestRace:
    """race: all providers answer, first valid response wins."""

    def test_race_success(self, mock_llm_registry):
        """Should return a winner + all responses."""
        result = swarm(action="race", question="What is 2+2?")
        assert result["status"] == "success"
        data = result["data"]
        assert data["winner"] is not None
        assert data["winner"]["text"] != ""
        assert data["provider_count"] == 3
        assert len(data["responses"]) >= 1

    def test_race_missing_question(self, mock_llm_registry):
        """Should fail if question is empty."""
        result = swarm(action="race")
        assert result["status"] == "error"
        assert "question is required" in result["error"]

    def test_race_no_providers(self, mock_llm_empty_registry):
        """Should fail when no cloud providers configured."""
        result = swarm(action="race", question="test")
        assert result["status"] == "error"
        assert "No cloud providers" in result["error"]

    def test_race_all_providers_fail(self, mock_failing_providers):
        """Should fail when all providers return errors."""
        result = swarm(action="race", question="test")
        assert result["status"] == "error"
        assert "All providers failed" in result["error"]

    def test_race_provider_filter(self, mock_llm_registry):
        """Should only call filtered providers."""
        result = swarm(action="race", question="test", providers="openai")
        assert result["status"] == "success"
        assert result["data"]["provider_count"] == 1
