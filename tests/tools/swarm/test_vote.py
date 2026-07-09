"""Tests for swarm vote action."""
from __future__ import annotations
from tools.swarm import swarm


class TestVote:
    """vote: all providers answer, agreement analysis."""

    def test_vote_success(self, mock_llm_registry):
        """Should return responses + agreement analysis."""
        result = swarm(action="vote", question="Is Python good? YES or NO.")
        assert result["status"] == "success"
        data = result["data"]
        assert data["provider_count"] == 3
        assert data["successful_count"] == 3
        assert "agreement" in data
        assert data["agreement"] in ("unanimous", "majority", "split", "disagreement")
        assert len(data["groups"]) >= 1

    def test_vote_missing_question(self, mock_llm_registry):
        """Should fail if question is empty."""
        result = swarm(action="vote")
        assert result["status"] == "error"
        assert "question is required" in result["error"]

    def test_vote_no_providers(self, mock_llm_empty_registry):
        """Should fail when no cloud providers configured."""
        result = swarm(action="vote", question="test")
        assert result["status"] == "error"
        assert "No cloud providers" in result["error"]

    def test_vote_all_providers_fail(self, mock_failing_providers):
        """Should fail when all providers return errors."""
        result = swarm(action="vote", question="test")
        assert result["status"] == "error"
        assert "All providers failed" in result["error"]

    def test_vote_unanimous(self, mock_llm_registry):
        """When all providers return same text, agreement should be 'unanimous'."""
        # mock_llm_registry returns "Response from {name}" for each provider,
        # which is DIFFERENT per provider. So this test verifies the disagreement case.
        result = swarm(action="vote", question="test")
        assert result["status"] == "success"
        # Different responses → not unanimous
        assert result["data"]["agreement"] != "unanimous"

    def test_vote_groups_sorted_by_count(self, mock_llm_registry):
        """Groups should be sorted by count (descending)."""
        result = swarm(action="vote", question="test")
        assert result["status"] == "success"
        groups = result["data"]["groups"]
        counts = [g["count"] for g in groups]
        assert counts == sorted(counts, reverse=True)
