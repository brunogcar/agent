"""Agent tool tests — response caching for deterministic roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestAgentCaching:
    """Test cache hit, miss, TTL, and non-cacheable roles."""

    def setup_method(self):
        """Clear cache between tests."""
        _clear_cache()

    def test_classify_result_is_cached(self, mock_llm_result):
        """Second identical classify call should return cached result."""
        mock_llm_result.text = "bug"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            result1 = agent(action="dispatch", role="classify", task="Is this a bug?")
            result2 = agent(action="dispatch", role="classify", task="Is this a bug?")

            assert result1["status"] == "success"
            assert result2["status"] == "success"
            assert result2.get("cached") is True
            # LLM should only be called once
            assert mock_llm.call_count == 1

    def test_route_result_is_cached(self, mock_llm_result):
        """route role should also be cached."""
        mock_llm_result.text = '{"workflow": "research"}'

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="route", task="Where to?")
            agent(action="dispatch", role="route", task="Where to?")

            assert mock_llm.call_count == 1

    def test_cache_respects_context_and_content(self, mock_llm_result):
        """Different context should result in separate cache entries."""
        mock_llm_result.text = "bug"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="classify", task="Is this a bug?", context="Python")
            agent(action="dispatch", role="classify", task="Is this a bug?", context="JavaScript")

            # Two different contexts = two LLM calls
            assert mock_llm.call_count == 2

    def test_non_cacheable_roles_not_cached(self, mock_llm_result):
        """research role should not be cached."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="research", task="Find docs")
            agent(action="dispatch", role="research", task="Find docs")

            assert mock_llm.call_count == 2

    def test_cache_ttl_expires(self, mock_llm_result):
        """Cached result should expire after TTL."""
        import time
        mock_llm_result.text = "bug"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm, patch("tools.agent_ops.cache._CACHE_TTL_SECONDS", 0):  # Instant expiry
            agent(action="dispatch", role="classify", task="test")
            time.sleep(0.01)
            agent(action="dispatch", role="classify", task="test")

            assert mock_llm.call_count == 2

    # ─── Cache limits configurable (Bug #19) ─────────────────────────────────

    def test_cache_max_read_from_cfg(self):
        """_CACHE_MAX must reflect cfg.agent_cache_max, not be hardcoded 100."""
        from tools.agent_ops import cache as cache_mod
        from core.config import cfg
        assert cache_mod._CACHE_MAX == cfg.agent_cache_max, (
            f"_CACHE_MAX={cache_mod._CACHE_MAX} must equal cfg.agent_cache_max={cfg.agent_cache_max}"
        )

    def test_cache_ttl_read_from_cfg(self):
        """_CACHE_TTL_SECONDS must reflect cfg.agent_cache_ttl_seconds."""
        from tools.agent_ops import cache as cache_mod
        from core.config import cfg
        assert cache_mod._CACHE_TTL_SECONDS == cfg.agent_cache_ttl_seconds, (
            f"_CACHE_TTL_SECONDS={cache_mod._CACHE_TTL_SECONDS} must equal "
            f"cfg.agent_cache_ttl_seconds={cfg.agent_cache_ttl_seconds}"
        )

    # ─── Cache key includes model name (Bug #23) ─────────────────────────────

    def test_cache_key_includes_model_name(self):
        """Different models must produce different cache keys.

        Without the model in the key, swapping models (e.g., during benchmark
        overrides) returns stale cache hits from the previous model.
        """
        from tools.agent_ops.cache import _cache_key
        key1 = _cache_key("classify", "task", "ctx", "content", model="model-a")
        key2 = _cache_key("classify", "task", "ctx", "content", model="model-b")
        assert key1 != key2, (
            "Cache keys must differ when model differs — stale hits on model swap."
        )

    def test_cache_key_same_model_same_key(self):
        """Same model must produce the same cache key."""
        from tools.agent_ops.cache import _cache_key
        key1 = _cache_key("classify", "task", "ctx", "content", model="model-a")
        key2 = _cache_key("classify", "task", "ctx", "content", model="model-a")
        assert key1 == key2

    def test_cache_key_backward_compatible_without_model(self):
        """Callers that don't pass model should get the old behavior."""
        from tools.agent_ops.cache import _cache_key
        key1 = _cache_key("classify", "task", "ctx", "content")
        key2 = _cache_key("classify", "task", "ctx", "content", model="")
        assert key1 == key2
