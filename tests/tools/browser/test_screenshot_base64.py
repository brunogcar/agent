"""Browser tool tests — screenshot base64 encoding."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock, mock_open
from tools.browser import browser


class TestScreenshotBase64:
    """Test screenshot base64 return."""

    def test_screenshot_returns_base64(self, mock_browser, tmp_path):
        """Mock the file read to return PNG bytes and verify base64 is returned."""
        with patch("tools.browser_core.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            # Mock open() to return fake PNG bytes when the handler reads the file
            fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            with patch("builtins.open", mock_open(read_data=fake_png)):
                result = browser(
                    action="screenshot", return_base64=True, trace_id="t1"
                )
                assert result["status"] == "success"
                assert "path" in result["data"]
                assert "base64" in result["data"]
                assert len(result["data"]["base64"]) > 0

    def test_screenshot_no_base64_by_default(self, mock_browser, tmp_path):
        with patch("tools.browser_core.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            result = browser(action="screenshot", trace_id="t1")
            assert result["status"] == "success"
            assert "base64" not in result["data"]
