"""Agent tool tests — budget_chars=0 edge case."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestBudgetCharsZero:
    """Test that budget_chars=0 is respected and not overridden by _max_context_chars()."""

    def setup_method(self):
        _clear_cache()

    def test_budget_chars_zero_not_overridden(self, mock_llm_result):
        """budget_chars=0 must not fall through to _max_context_chars().

        The 'or' trap bug: `budget_chars = role_cfg.get("budget_chars") or _max_context_chars()`
        would treat 0 as falsy and use _max_context_chars() instead.
        With the fix (is None check), budget_chars=0 is respected.

        We verify this by checking the context is NOT the full untrimmed text
        (which would happen if _max_context_chars() was used and the text fit).
        """
        from tools.agent_ops import ROLES
        original_chars = ROLES["classify"]["role_config"].get("budget_chars")
        original_tokens = ROLES["classify"]["role_config"].get("budget_tokens")
        try:
            # Remove budget_tokens so budget_chars=0 takes effect
            ROLES["classify"]["role_config"]["budget_chars"] = 0
            if "budget_tokens" in ROLES["classify"]["role_config"]:
                del ROLES["classify"]["role_config"]["budget_tokens"]

            with patch("tools.agent_ops.actions.dispatch.llm.complete") as mock_llm:
                mock_llm.return_value = mock_llm_result
                agent(action="dispatch", role="classify", task="test", context="x" * 1000)
                call_kwargs = mock_llm.call_args.kwargs
                # If _max_context_chars() was used (the bug), "x"*1000 would fit
                # in 32000 char budget and return unchanged (1000 chars).
                # With budget_chars=0 respected, it should be different.
                assert len(call_kwargs["context"]) != 1000, (
                    "budget_chars=0 was overridden by _max_context_chars() — "
                    "the 'or' trap bug is still present"
                )
        finally:
            if original_chars is not None:
                ROLES["classify"]["role_config"]["budget_chars"] = original_chars
            else:
                del ROLES["classify"]["role_config"]["budget_chars"]
            if original_tokens is not None:
                ROLES["classify"]["role_config"]["budget_tokens"] = original_tokens
