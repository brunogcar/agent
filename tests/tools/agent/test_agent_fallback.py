"""Agent tool tests — retry with fallback role on transient failure."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestRoleFallback:
    """Test fallback role retry when primary role's LLM call fails."""

    def setup_method(self):
        from tools.agent import _CACHE
        _CACHE.clear()

    def test_classify_fallback_to_route(self, mock_llm_result):
        """When classify fails, retry with route role."""
        fail_result = type("obj", (object,), {
            "ok": False, "error": "Router model timed out", "elapsed": 15.0, "model": "router"
        })()
        success_result = type("obj", (object,), {
            "ok": True, "text": '{"category": "bug"}', "parsed": None,
            "model": "router", "elapsed": 2.0, "usage": {"total_tokens": 15}
        })()

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.side_effect = [fail_result, success_result]
            result = agent(role="classify", task="Is this a bug?")

        assert result["status"] == "success"
        assert result["text"] == '{"category": "bug"}'
        assert mock_llm.call_count == 2
        # Second call should use route's system prompt
        second_call = mock_llm.call_args_list[1]
        assert "route" in second_call.kwargs["system"].lower() or "router" in second_call.kwargs["system"].lower()

    def test_critique_fallback_to_analyze(self, mock_llm_result):
        """When critique fails, retry with analyze role."""
        fail_result = type("obj", (object,), {
            "ok": False, "error": "Timeout", "elapsed": 90.0, "model": "critique"
        })()
        success_result = type("obj", (object,), {
            "ok": True, "text": "Analysis: code has race condition", "parsed": None,
            "model": "analyze", "elapsed": 5.0, "usage": {"total_tokens": 100}
        })()

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.side_effect = [fail_result, success_result]
            result = agent(role="critique", task="Review this code")

        assert result["status"] == "success"
        assert mock_llm.call_count == 2

    def test_no_fallback_when_no_fallback_role(self, mock_llm_result):
        """plan role has no fallback — should return error on failure."""
        fail_result = type("obj", (object,), {
            "ok": False, "error": "Timeout", "elapsed": 90.0, "model": "planner"
        })()

        with patch("tools.agent.llm.complete", return_value=fail_result) as mock_llm:
            result = agent(role="plan", task="Plan this")

        assert result["status"] == "error"
        assert mock_llm.call_count == 1

    def test_fallback_failure_returns_error(self, mock_llm_result):
        """If both primary and fallback fail, return error."""
        fail1 = type("obj", (object,), {
            "ok": False, "error": "Timeout", "elapsed": 15.0, "model": "router"
        })()
        fail2 = type("obj", (object,), {
            "ok": False, "error": "Also failed", "elapsed": 15.0, "model": "router"
        })()

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.side_effect = [fail1, fail2]
            result = agent(role="classify", task="test")

        assert result["status"] == "error"
        assert mock_llm.call_count == 2
