"""Browser tool tests — keyboard_press action."""
from __future__ import annotations

from tools.browser import browser


class TestKeyboardPress:
    """Test browser keyboard_press action."""

    def test_keyboard_press_success(self, mock_browser):
        result = browser(action="keyboard_press", key="Enter", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["pressed"] == "Enter"
        mock_browser["page"].keyboard.press.assert_called_once_with("Enter")

    def test_keyboard_press_missing_key(self, mock_browser):
        result = browser(action="keyboard_press", trace_id="t1")
        assert result["status"] == "error"
        assert "key is required" in result["error"]
