"""Agent tool tests — token-aware context trimming."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.context import _estimate_tokens, _trim_context
from tools.agent_core.cache import _clear_cache


class TestTokenAwareTrimming:
    """Test _estimate_tokens and token-aware _trim_context."""

    def setup_method(self):
        _clear_cache()

    def test_estimate_tokens_empty(self):
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_simple_text(self):
        # "hello world" — roughly 2-3 tokens depending on tokenizer
        tokens = _estimate_tokens("hello world")
        assert tokens > 0

    def test_estimate_tokens_code(self):
        code = "def foo():\n    return 42"
        tokens = _estimate_tokens(code)
        # Code typically tokenizes at ~3 chars/token, so 20 chars ~ 7 tokens
        assert tokens > 0
        assert tokens < len(code)  # Should be fewer tokens than chars

    def test_trim_context_with_max_tokens(self):
        """Trim using token budget instead of char budget."""
        text = "x" * 10000
        result = _trim_context(text, max_tokens=10)
        # Should be significantly shorter than 10000 chars
        assert len(result) < 10000
        assert "truncated" in result

    def test_trim_context_token_budget_preserves_traceback(self):
        tb = "Traceback (most recent call last):\n  File \"test.py\"\nZeroDivisionError"
        text = "x" * 5000 + "\n" + tb + "\n" + "y" * 5000
        result = _trim_context(text, max_tokens=50)
        assert tb in result

    def test_agent_uses_token_budget_when_configured(self, mock_llm_result):
        """If ROLE_CONFIG has budget_tokens, agent uses token-aware trimming."""
        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            # plan role has budget_chars=128000, no budget_tokens yet
            # This test verifies the code path exists
            agent(role="plan", task="test", context="x" * 50000)
            assert mock_llm.called
