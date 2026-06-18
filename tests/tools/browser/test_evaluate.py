"""Browser tool tests — evaluate action."""
from __future__ import annotations

from tools.browser import browser


class TestEvaluate:
    """Test browser evaluate action."""

    def test_evaluate_success(self, mock_browser):
        result = browser(action="evaluate", expression="document.title", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["result"] == "eval_result"
        assert result["data"]["expression"] == "document.title"

    def test_evaluate_missing_expression(self, mock_browser):
        result = browser(action="evaluate", trace_id="t1")
        assert result["status"] == "error"
        assert "expression is required" in result["error"]
