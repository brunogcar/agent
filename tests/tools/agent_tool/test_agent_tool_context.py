"""Test agent_tool context trimming."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from tools.agent_tool import _trim_context, _MAX_CONTEXT_CHARS, _KEEP_HEAD_CHARS, _KEEP_TAIL_CHARS

class TestTrimContextUnit:
    """Unit tests for _trim_context."""

    def test_short_text_unchanged(self):
        text = "short context"
        assert _trim_context(text) == text

    def test_empty_text(self):
        assert _trim_context("") == ""
        assert _trim_context(None) is None

    def test_exactly_at_budget(self):
        text = "x" * _MAX_CONTEXT_CHARS
        assert _trim_context(text) == text

    def test_head_plus_tail_fits(self):
        """If text fits within head+tail budget, return as-is."""
        text = "x" * (_KEEP_HEAD_CHARS + _KEEP_TAIL_CHARS - 1)
        assert _trim_context(text) == text

    def test_long_text_preserves_head_and_tail(self):
        """Long text should keep head and tail, truncate middle."""
        # [BUGFIX-5] _MAX_CONTEXT_CHARS is now cfg.max_context_tokens * 4 (~32000).
        # Use a middle section that exceeds the budget to force truncation.
        head = "GOAL: audit all files for security\n\n"
        middle = "x" * (_MAX_CONTEXT_CHARS + 1000)
        tail = "\n\nRecent: tool_call result here"
        text = head + middle + tail

        result = _trim_context(text)
        assert "GOAL: audit all files" in result
        assert "Recent: tool_call result" in result
        assert "truncated" in result
        assert middle not in result

    def test_truncation_notice_includes_count(self):
        # [BUGFIX-5] Use text larger than the dynamic _MAX_CONTEXT_CHARS.
        text = "x" * (_MAX_CONTEXT_CHARS + 1000)
        result = _trim_context(text)
        assert "chars of intermediate context truncated" in result

    def test_custom_max_chars(self):
        text = "x" * 1000
        result = _trim_context(text, max_chars=500)
        assert len(result) < len(text)
        assert "truncated" in result
        # Verify custom budget respected: head ~167, tail ~333, total ~500
        assert len(result) < 600

class TestTrimContextIntegration:
    """Verify _trim_context is called in the agent() function."""

    def test_trim_called_on_context(self):
        """Mock _trim_context and verify it's called with context."""
        with patch("tools.agent_tool._trim_context") as mock_trim:
            mock_trim.side_effect = lambda x, **kw: x # pass-through
            with patch("tools.agent_tool.llm.complete") as mock_llm:
                mock_llm.return_value = MagicMock(ok=True, text="done", finish_reason="stop")
                from tools.agent_tool import agent
                agent(role="plan", task="test", context="some context")
                # _trim_context should be called at least once for context
                mock_trim.assert_called()
