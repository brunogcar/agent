"""tests/workflows/data/test_helpers.py
Tests for the _extract_code_from_response helper.
"""
from __future__ import annotations

from workflows.data_impl.helpers import _extract_code_from_response


class TestExtractCodeFromResponse:
    def test_extracts_from_parsed_patch(self):
        """Preferred path: structured parsed['patch'] field."""
        parsed = {"patch": "print(sum([1, 2, 3]))", "analysis": "sums a list"}
        code = _extract_code_from_response(parsed, "ignored", trace_id="t1")
        assert code == "print(sum([1, 2, 3]))"

    def test_extracts_from_fence_fallback(self):
        """[Fix #9] When no patch, fall back to a ```python fence."""
        text = "Here is the code:\n```python\nprint('hello')\n```\nDone."
        code = _extract_code_from_response(None, text, trace_id="t1")
        assert "print('hello')" in code

    def test_extracts_from_bare_fence_fallback(self):
        """Fence without a language tag also matches."""
        text = "```\nprint(42)\n```"
        code = _extract_code_from_response({}, text, trace_id="t1")
        assert "print(42)" in code

    def test_falls_back_to_raw_text(self):
        """[Fix #9] When no patch and no fence, use raw text (last resort)."""
        text = "print('no fence here')"
        code = _extract_code_from_response(None, text, trace_id="t1")
        assert code == "print('no fence here')"

    def test_empty_inputs_returns_empty(self):
        assert _extract_code_from_response(None, "", trace_id="t1") == ""

    def test_blank_patch_falls_through(self):
        """A blank/empty patch must not short-circuit the fallbacks."""
        code = _extract_code_from_response({"patch": "   "}, "```python\nx=1\n```", "t1")
        assert "x=1" in code
