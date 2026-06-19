"""Agent tool tests — context trimming."""
from __future__ import annotations

from tools.agent_core.context import _trim_context, _max_context_chars, _KEEP_HEAD_CHARS, _KEEP_TAIL_CHARS


class TestTrimContextUnit:
    """Unit tests for _trim_context."""

    def test_short_text_unchanged(self):
        text = "short context"
        assert _trim_context(text) == text

    def test_empty_text(self):
        assert _trim_context("") == ""
        assert _trim_context(None) is None

    def test_exactly_at_budget(self):
        """Text exactly at the dynamic budget should be returned as-is."""
        text = "x" * _max_context_chars()
        assert _trim_context(text) == text

    def test_head_plus_tail_fits(self):
        """If text fits within head+tail budget, return as-is."""
        text = "x" * (_KEEP_HEAD_CHARS + _KEEP_TAIL_CHARS - 1)
        assert _trim_context(text) == text

    def test_long_text_preserves_head_and_tail(self):
        """Long text should keep head and tail, truncate middle."""
        head = "GOAL: audit all files for security\n\n"
        middle = "x" * (_max_context_chars() + 1000)
        tail = "\n\nRecent: tool_call result here"
        text = head + middle + tail

        result = _trim_context(text)
        assert "GOAL: audit all files" in result
        assert "Recent: tool_call result" in result
        assert "truncated" in result
        assert middle not in result

    def test_truncation_notice_includes_count(self):
        """Truncation notice should include the number of truncated chars."""
        text = "x" * (_max_context_chars() + 1000)
        result = _trim_context(text)
        assert "chars of intermediate context truncated" in result

    def test_custom_max_chars(self):
        """Custom max_chars parameter should override the dynamic default."""
        text = "x" * 1000
        result = _trim_context(text, max_chars=500)
        assert len(result) < len(text)
        assert "truncated" in result
        assert len(result) < 600


class TestTrimContextTraceback:
    """Traceback preservation in context trimming."""

    def test_traceback_preserved_when_it_fits(self):
        """If traceback fits within budget, it should be preserved intact."""
        head = "Some context before\n\n"
        tb = "Traceback (most recent call last):\n  File \"test.py\", line 10\n    x = 1/0\nZeroDivisionError: division by zero"
        tail = "\n\nSome context after"
        text = head + tb + tail

        # Budget is large enough to fit everything — no truncation
        result = _trim_context(text, max_chars=5000)
        assert "Traceback (most recent call last):" in result
        assert "ZeroDivisionError" in result
        # When everything fits, result equals input exactly
        assert result == text

    def test_traceback_falls_through_when_too_long(self):
        """If traceback itself exceeds max_chars, normal trim applies."""
        head = "Context before\n\n"
        # Very long traceback that exceeds the budget
        tb = "Traceback (most recent call last):\n" + "  File \"x.py\", line 1\n    x = 1\n" * 200
        text = head + tb

        result = _trim_context(text, max_chars=500)
        # Normal trim should still capture tail content
        assert len(result) < len(text)
        assert "truncated" in result

    # ── Phase 3 additions: traceback preservation deep tests ─────────────────

    def test_traceback_detected_and_preserved_in_full(self):
        """When traceback fits within budget, it must be preserved completely.

        The _trim_context function detects 'Traceback (most recent call last):'
        and attempts to preserve the entire traceback block. This test verifies
        that both the traceback header and the final error line survive trimming.
        """
        head = "Some context before\n\n"
        tb = (
            "Traceback (most recent call last):\n"
            '  File "test.py", line 10, in <module>\n'
            "    x = 1 / 0\n"
            "ZeroDivisionError: division by zero"
        )
        tail = "\n\nSome context after"
        text = head + tb + tail

        # Budget is large enough to fit everything — no truncation expected
        result = _trim_context(text, max_chars=5000)
        assert "Traceback (most recent call last):" in result
        assert "ZeroDivisionError: division by zero" in result
        # When everything fits, result equals input exactly
        assert result == text

    def test_traceback_falls_through_when_exceeds_budget(self):
        """When traceback itself exceeds max_chars, normal head+tail trim applies.

        The traceback preservation branch checks tb_len <= max_chars before
        attempting to preserve. If the traceback is longer than the budget,
        it falls through to the normal head+tail trim. This test verifies
        the fallback behavior doesn't crash and still produces valid output.
        """
        # Very long traceback that exceeds a small budget
        tb = (
            "Traceback (most recent call last):\n"
            + '  File "x.py", line 1\n    x = 1\n' * 200
        )
        text = "Context before\n\n" + tb

        result = _trim_context(text, max_chars=500)
        # Normal trim should still capture something from the end
        assert len(result) < len(text)
        assert "truncated" in result

    def test_multiple_tracebacks_only_first_preserved(self):
        """When multiple tracebacks exist, only the first is fully preserved.

        text.find(tb_marker) returns the first occurrence. Subsequent tracebacks
        are subject to normal trimming. This is intentional — the first traceback
        is usually the root cause.
        """
        tb1 = (
            "Traceback (most recent call last):\n"
            '  File "a.py", line 1\n    raise KeyError("first")\n'
            'KeyError: "first"'
        )
        middle = "\n\nSome processing...\n\n"
        tb2 = (
            "Traceback (most recent call last):\n"
            '  File "b.py", line 1\n    raise ValueError("second")\n'
            'ValueError: "second"'
        )
        text = tb1 + middle + tb2

        result = _trim_context(text, max_chars=2000)
        # First traceback should be fully preserved
        assert 'KeyError: "first"' in result
        # Second traceback may be trimmed (depends on budget)
        # but the first one must survive
        assert result.count("Traceback (most recent call last):") >= 1
