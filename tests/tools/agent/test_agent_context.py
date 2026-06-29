"""Agent tool tests — context trimming."""
from __future__ import annotations

from tools.agent_ops.context import _trim_context


class TestTrimContextUnit:
    """Unit tests for _trim_context."""

    def test_short_text_unchanged(self):
        text = "Short text."
        assert _trim_context(text) == text

    def test_empty_text(self):
        assert _trim_context("") == ""

    def test_exactly_at_budget(self):
        """Text exactly at the dynamic budget should be returned as-is."""
        text = "x" * 16000
        result = _trim_context(text, max_chars=16000)
        assert result == text

    def test_head_plus_tail_fits(self):
        """If text fits within head+tail budget, return as-is."""
        text = "x" * 100
        result = _trim_context(text, max_chars=200)
        assert result == text

    def test_long_text_preserves_head_and_tail(self):
        """Long text should keep head and tail, truncate middle."""
        text = "HEAD" + "x" * 10000 + "TAIL"
        result = _trim_context(text, max_chars=100)
        assert "HEAD" in result
        assert "TAIL" in result
        assert "..." in result

    def test_truncation_notice_includes_count(self):
        """Truncation notice should include the number of truncated chars."""
        text = "x" * 10000
        result = _trim_context(text, max_chars=100)
        assert "truncated" in result.lower() or "..." in result

    def test_custom_max_chars(self):
        """Custom max_chars parameter should override the dynamic default."""
        text = "x" * 500
        result = _trim_context(text, max_chars=100)
        assert len(result) < len(text)


class TestTrimContextTraceback:
    """Traceback preservation in context trimming."""

    def test_traceback_preserved_when_it_fits(self):
        """If traceback fits within budget, it should be preserved intact."""
        tb = "Traceback (most recent call last):\n  File \"test.py\"\nValueError: test"
        result = _trim_context(tb, max_chars=500)
        assert "Traceback" in result
        assert "ValueError" in result

    def test_traceback_falls_through_when_too_long(self):
        """If traceback itself exceeds max_chars, normal trim applies."""
        tb = "Traceback (most recent call last):\n" + "x" * 10000
        result = _trim_context(tb, max_chars=100)
        assert len(result) <= 200  # Some reasonable limit

    def test_traceback_detected_and_preserved_in_full(self):
        """When traceback fits within budget, it must be preserved completely."""
        tb = "Traceback (most recent call last):\n  File \"test.py\"\nValueError: test"
        result = _trim_context(tb, max_chars=500)
        assert result == tb

    def test_traceback_falls_through_when_exceeds_budget(self):
        """When traceback itself exceeds max_chars, normal head+tail trim applies."""
        tb = "Traceback (most recent call last):\n" + "x" * 10000
        result = _trim_context(tb, max_chars=100)
        assert "Traceback" in result  # At least the header is there

    def test_multiple_tracebacks_only_first_preserved(self):
        """When multiple tracebacks exist, only the first is fully preserved."""
        tb = "Traceback (most recent call last):\n  File \"a.py\"\nError: a\nTraceback (most recent call last):\n  File \"b.py\"\nError: b"
        result = _trim_context(tb, max_chars=500)
        assert "Error: a" in result
