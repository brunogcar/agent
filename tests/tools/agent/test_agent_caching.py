"""Agent tool tests — response caching for deterministic roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentCaching:
    """Test in-memory LRU cache for classify and route roles."""

    def setup_method(self):
        """Clear response cache between tests."""
        from tools.agent import _CACHE
        _CACHE.clear()

    def test_classify_result_is_cached(self, mock_llm_result):
        """Second identical classify call should return cached result."""
        mock_llm_result.text = "bug"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm:
            result1 = agent(role="classify", task="Is this a bug?")
            result2 = agent(role="classify", task="Is this a bug?")

            assert result1["status"] == "success"
            assert result2["status"] == "success"
            assert result2.get("cached") is True
            # LLM should only be called once
            assert mock_llm.call_count == 1

    def test_route_result_is_cached(self, mock_llm_result):
        """Second identical route call should return cached result."""
        mock_llm_result.text = '{"workflow":"research","tool":"web","complexity":3,"reason":"test"}'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm:
            result1 = agent(role="route", task="Find docs")
            result2 = agent(role="route", task="Find docs")

            assert result1["status"] == "success"
            assert result2.get("cached") is True
            assert mock_llm.call_count == 1

    def test_cache_respects_context_and_content(self, mock_llm_result):
        """Different context should result in separate cache entries."""
        mock_llm_result.text = "bug"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(role="classify", task="Is this a bug?", context="Python")
            agent(role="classify", task="Is this a bug?", context="JavaScript")

            # Two different contexts = two LLM calls
            assert mock_llm.call_count == 2

    def test_non_cacheable_roles_not_cached(self, mock_llm_result):
        """research role should not be cached."""
        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(role="research", task="Find docs")
            agent(role="research", task="Find docs")

            assert mock_llm.call_count == 2

    def test_cache_ttl_expires(self, mock_llm_result):
        """Cached result should expire after TTL."""
        import time
        mock_llm_result.text = "bug"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm, \
             patch("tools.agent._CACHE_TTL_SECONDS", 0):  # Instant expiry
            agent(role="classify", task="test")
            time.sleep(0.01)
            agent(role="classify", task="test")

            assert mock_llm.call_count == 2
