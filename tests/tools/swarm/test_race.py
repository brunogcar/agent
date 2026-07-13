"""Tests for swarm race action.

v1.0.1: Added test_race_returns_fast (P1-2 regression) — verifies that race
returns as soon as the first valid response lands, without blocking on
slower providers. Under v1.0's broken implementation (as_completed + break
+ ThreadPoolExecutor.__exit__ shutdown(wait=True)), race blocked for the
slowest provider.
"""
from __future__ import annotations
import time
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

    def test_race_returns_fast(self, mock_providers_with_slow_one):
        """v1.0.1 regression (P1-2): race must return as soon as the fast
        provider responds, without waiting for the slow one.

        Under v1.0, ThreadPoolExecutor.__exit__ called shutdown(wait=True),
        blocking for the slow provider's full 2s sleep. The fix uses
        shutdown(wait=False, cancel_fories=True). We assert race returns in
        <1.0s (well under the slow provider's 2s, well above the fast
        provider's 0.3s) with the fast provider as the winner.

        Both providers use real time.sleep (not instant returns) so the slow
        future is RUNNING (not PENDING) when the winner is found — this is
        the condition under which v1.0 blocked. If the fast provider returned
        instantly, v1.0's f.cancel() would succeed on the still-pending slow
        future and the bug wouldn't reproduce.
        """
        start = time.monotonic()
        result = swarm(action="race", question="test", timeout=10)
        elapsed = time.monotonic() - start

        assert result["status"] == "success"
        # The fast provider (openai) should win
        assert result["data"]["winner"]["provider"] == "openai"
        assert result["data"]["winner"]["text"] == "fast response"
        # Must return well before the slow provider's 2s sleep finishes.
        # 1.0s gives generous slack above the fast provider's 0.3s and well
        # below the slow provider's 2.0s. v1.0 would take ~2.0s here.
        assert elapsed < 1.0, (
            f"race took {elapsed:.2f}s — expected <1.0s. "
            "v1.0 bug: ThreadPoolExecutor.__exit__ blocks on shutdown(wait=True)."
        )

    def test_race_winner_first_in_responses(self, mock_providers_with_slow_one):
        """v1.0.1 (P1-2): winner must be the first entry in responses list.

        Race semantics require 'who won' ordering — _call_providers_race must
        NOT sort by provider name (see INSTRUCTIONS.md #8).
        """
        result = swarm(action="race", question="test", timeout=10)
        assert result["status"] == "success"
        responses = result["data"]["responses"]
        assert len(responses) >= 1
        # First response should be the winner
        assert responses[0]["provider"] == result["data"]["winner"]["provider"]
