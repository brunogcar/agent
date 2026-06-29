"""Browser tool tests — set_viewport action."""
from __future__ import annotations

from unittest.mock import patch
from tools.browser import browser


class TestSetViewport:
    """Test browser set_viewport action."""

    def test_set_viewport_success(self, mock_browser):
        result = browser(
            action="set_viewport", width=1920, height=1080, trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["viewport_set"] is True
        assert result["data"]["width"] == 1920
        assert result["data"]["height"] == 1080
        mock_browser["page"].set_viewport_size.assert_called_once_with(
            {"width": 1920, "height": 1080}
        )

    def test_set_viewport_default(self, mock_browser):
        result = browser(action="set_viewport", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["width"] == 1280
        assert result["data"]["height"] == 720

    def test_set_viewport_passes_headless(self, mock_browser):
        """headless param must be forwarded to _get_page."""
        with patch(
            "tools.browser_ops.actions.set_viewport._get_page"
        ) as mock_get_page:
            mock_get_page.return_value = mock_browser["page"]
            browser(
                action="set_viewport",
                width=800,
                height=600,
                headless=False,
                trace_id="t1",
            )
            mock_get_page.assert_called_once_with("t1", False)
