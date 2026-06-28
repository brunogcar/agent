"""Browser tool tests — screenshot base64 encoding."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock
from tools.browser import browser


class TestScreenshotBase64:
    """Test screenshot base64 return."""

    def test_screenshot_returns_base64(self, mock_browser, tmp_path):
        with patch("tools.browser_core.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            result = browser(action="screenshot", return_base64=True, trace_id="t1")
            assert result["status"] == "success"
            assert "path" in result["data"]

    def test_screenshot_no_base64_by_default(self, mock_browser, tmp_path):
        with patch("tools.browser_core.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            result = browser(action="screenshot", trace_id="t1")
            assert result["status"] == "success"
            assert "base64" not in result["data"]
