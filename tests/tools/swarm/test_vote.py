"""Tests for swarm vote action.

v1.0.1: Expanded agreement-classification coverage:
  - test_vote_disagreement_distinct (renamed from test_vote_unanimous, which
    was misnamed — the mock returns DIFFERENT text per provider).
  - test_vote_unanimous (NEW — all providers return identical text).
  - test_vote_majority (NEW — 2-of-3 same).
  - test_vote_split (NEW — 2v2 tie, was misclassified as disagreement in v1.0).
  - test_vote_single_response (NEW — only 1 provider succeeded, was
    misclassified as unanimous in v1.0).
"""
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
        assert data["agreement"] in ("unanimous", "majority", "split", "disagreement", "single_response")
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

    def test_vote_disagreement_distinct(self, mock_llm_registry):
        """3 providers, 3 different responses → disagreement (not unanimous).

        v1.0.1: Renamed from test_vote_unanimous (which was misnamed — the
        mock_llm_registry fixture returns 'Response from {name}' per provider,
        so the responses are DIFFERENT). This test now verifies the disagreement
        case explicitly.
        """
        result = swarm(action="vote", question="test")
        assert result["status"] == "success"
        # 3 distinct responses → disagreement
        assert result["data"]["agreement"] == "disagreement"

    def test_vote_unanimous(self, make_vote_providers):
        """All providers return identical text → unanimous."""
        llm = make_vote_providers({
            "openai": "YES",
            "claude": "YES",
            "deepseek": "YES",
        })
        next(llm)  # enter the patched context
        result = swarm(action="vote", question="Is it safe? YES or NO.")
        assert result["status"] == "success"
        assert result["data"]["agreement"] == "unanimous"
        assert len(result["data"]["groups"]) == 1
        assert result["data"]["groups"][0]["count"] == 3

    def test_vote_majority(self, make_vote_providers):
        """2-of-3 same → majority."""
        llm = make_vote_providers({
            "openai": "YES",
            "claude": "YES",
            "deepseek": "NO",
        })
        next(llm)
        result = swarm(action="vote", question="Is it safe? YES or NO.")
        assert result["status"] == "success"
        assert result["data"]["agreement"] == "majority"
        # Largest group first (sorted by count desc)
        assert result["data"]["groups"][0]["count"] == 2
        assert result["data"]["groups"][1]["count"] == 1

    def test_vote_split(self, make_vote_providers):
        """2v2 tie → split (was misclassified as disagreement in v1.0).

        v1.0.1 regression: v1.0 had `len(successful) > 2` guard that pushed
        2-successful-2-distinct into the `else: disagreement` branch.
        """
        llm = make_vote_providers({
            "openai": "YES",
            "claude": "NO",
        })
        next(llm)
        result = swarm(action="vote", question="Is it safe? YES or NO.")
        assert result["status"] == "success"
        assert result["data"]["agreement"] == "split"
        assert len(result["data"]["groups"]) == 2
        # Both groups have count 1 — no majority
        counts = [g["count"] for g in result["data"]["groups"]]
        assert counts == [1, 1]

    def test_vote_single_response(self, make_vote_providers):
        """Only 1 provider succeeds → single_response (was unanimous in v1.0).

        v1.0.1 regression: v1.0 had `len(normalized) == 1 → unanimous`,
        which is semantically wrong for a single voter. Downstream consumers
        (autocode debug-loop confidence_map) treat `unanimous` as HIGH
        confidence; a single-response verdict must NOT be HIGH.
        """
        # 2 providers configured; claude fails (None), openai succeeds.
        llm = make_vote_providers({
            "openai": "YES",
            "claude": None,
        })
        next(llm)
        result = swarm(action="vote", question="Is it safe? YES or NO.")
        assert result["status"] == "success"
        assert result["data"]["successful_count"] == 1
        assert result["data"]["agreement"] == "single_response"

    def test_vote_groups_sorted_by_count(self, mock_llm_registry):
        """Groups should be sorted by count (descending)."""
        result = swarm(action="vote", question="test")
        assert result["status"] == "success"
        groups = result["data"]["groups"]
        counts = [g["count"] for g in groups]
        assert counts == sorted(counts, reverse=True)

    def test_vote_whitespace_only_not_unanimous(self, make_vote_providers):
        """v1.0.2 (P1-3 cross-LLM): Two whitespace-only responses must NOT
        be classified as unanimous. v1.0.1 bug: "   " was truthy, passed the
        filter, then normalized to "" — so two whitespace responses falsely
        grouped as unanimous with key "".
        """
        llm = make_vote_providers({
            "openai": "   ",    # whitespace only
            "claude": "   ",    # whitespace only
        })
        next(llm)
        result = swarm(action="vote", question="test")
        # Both providers returned whitespace — should be filtered out as failures.
        # With 0 successful responses, the action fails with "All providers failed".
        assert result["status"] == "error"
        assert "All providers failed" in result["error"]
