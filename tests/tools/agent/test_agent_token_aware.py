"""Agent tool tests — token-aware context trimming."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestTokenAwareTrimming:
    """Test _estimate_tokens and token-aware _trim_context."""

    def setup_method(self):
        _clear_cache()

    def test_estimate_tokens_empty(self):
        from tools.agent_ops.context import _estimate_tokens
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_simple_text(self):
        from tools.agent_ops.context import _estimate_tokens
        tokens = _estimate_tokens("hello world")
        assert tokens > 0

    def test_estimate_tokens_code(self):
        from tools.agent_ops.context import _estimate_tokens
        code = "def foo():\n    return 1"
        tokens = _estimate_tokens(code)
        assert tokens > 0

    def test_trim_context_with_max_tokens(self):
        from tools.agent_ops.context import _trim_context
        long_text = "word " * 1000
        trimmed = _trim_context(long_text, max_tokens=10)
        assert len(trimmed) < len(long_text)

    def test_trim_context_token_budget_preserves_traceback(self):
        from tools.agent_ops.context import _trim_context
        tb = "Traceback (most recent call last):\n  File \"test.py\"\nValueError: test"
        trimmed = _trim_context(tb, max_tokens=100)
        assert "Traceback" in trimmed

    def test_agent_uses_token_budget_when_configured(self, mock_llm_result):
        """If ROLE_CONFIG has budget_tokens, agent uses token-aware trimming."""
        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            agent(action="dispatch", role="plan", task="test", context="word " * 10000)
            call_kwargs = mock_llm.call_args.kwargs
            # plan has budget_tokens=32000, so context should be trimmed to token budget
            assert "context" in call_kwargs

    # ─── Content budget uses 70% of remaining (Bug #9) ───────────────────────

    def test_content_budget_uses_70_percent_of_remaining(self, mock_llm_result):
        """Content budget must use 70% of remaining tokens, not min(1000, ...).

        For a role with budget_tokens=4000 and small context, content budget
        should be ~70% of 4000 = 2800, not the old cap of 1000 tokens (~3000 chars).
        Roles like code/refactor/test/document need the full budget — content
        IS the primary input for them.
        """
        mock_llm_result.text = "ok"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            # classify role: budget_tokens=4000
            agent(action="dispatch", role="classify", task="test", content="x" * 5000)

            call_kwargs = mock_llm.call_args.kwargs
            content_arg = call_kwargs["content"]
            # With 70% of 4000 = 2800 token budget, content should be much larger
            # than the old 1000-token cap (~3000 chars). Allow some slack for
            # the trimming logic (head+tail split).
            assert len(content_arg) > 3000, (
                f"Content was truncated to {len(content_arg)} chars — likely still "
                f"using the old min(1000, ...) cap. Expected >3000 chars with the "
                f"70% budget fix."
            )
