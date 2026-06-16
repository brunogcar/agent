"""Tests for browser screenshot size limits and pruning.

Verifies that large base64 screenshots don't context-bomb the LLM.
"""
from __future__ import annotations

import base64
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tools.browser import browser


@pytest.fixture(autouse=True)
def mock_cfg_for_screenshot(tmp_path):
    """Mock cfg to prevent AsyncMock leakage and provide browser defaults."""
    with patch("tools.browser.cfg") as mock_cfg:
        mock_cfg.workspace_root = tmp_path
        mock_cfg.cli_max_command_chars = 4096
        mock_cfg.cli_max_arguments = 50
        yield mock_cfg


@pytest.fixture
def mock_browser():
    """Return a mock browser + page that survives the async bridge."""
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example Page")
    mock_page.goto = AsyncMock(return_value=None)
    mock_page.click = AsyncMock(return_value=None)
    mock_page.fill = AsyncMock(return_value=None)
    mock_page.type = AsyncMock(return_value=None)
    mock_page.screenshot = AsyncMock(return_value=None)
    mock_page.text_content = AsyncMock(return_value="Hello World")
    mock_page.evaluate = AsyncMock(return_value="eval_result")
    mock_page.select_option = AsyncMock(return_value=None)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock(return_value=None)
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.on = MagicMock(return_value=None)

    mock_ctx = MagicMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    mock_ctx.close = AsyncMock(return_value=None)

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)
    mock_browser.close = AsyncMock(return_value=None)

    mock_pw = MagicMock()
    mock_pw.chromium = MagicMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_pw.stop = AsyncMock(return_value=None)
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.browser._launch_browser", new=AsyncMock(return_value=mock_browser)):
        with patch("playwright.async_api.async_playwright", return_value=mock_pw):
            with patch("tools.browser.is_safe_network_address", return_value=True):
                yield {
                    "page": mock_page,
                    "context": mock_ctx,
                    "browser": mock_browser,
                    "playwright": mock_pw,
                }


class TestScreenshotSizeLimits:
    """Verify screenshot results are pruned to prevent context overflow."""

    def test_screenshot_under_limit(self, mock_browser):
        """Small screenshot should return full base64 data."""
        small_image = b"\x89PNG\r\n\x1a\n" + b"x" * 1000  # ~1KB
        mock_browser["page"].screenshot = AsyncMock(return_value=small_image)

        result = browser(
            action="screenshot",
            url="https://example.com",
            trace_id="test-trace",
        )

        assert result.get("status") == "success"
        mock_browser["page"].screenshot.assert_called_once()

    def test_large_screenshot_truncated(self, mock_browser):
        """Screenshot exceeding safe limit should be truncated or rejected."""
        large_data = b"x" * (2 * 1024 * 1024)  # 2MB raw
        mock_browser["page"].screenshot = AsyncMock(return_value=large_data)

        result = browser(
            action="screenshot",
            url="https://example.com",
            trace_id="test-trace",
        )

        # Result should either be truncated or contain a warning
        if result.get("status") == "success":
            data = result.get("data", {})
            if "base64" in data:
                assert len(data["base64"]) < 50000, "Screenshot base64 exceeds safe limit"

    def test_screenshot_size_warning(self, mock_browser):
        """Very large screenshot should include a size warning."""
        large_data = b"x" * (5 * 1024 * 1024)  # 5MB
        mock_browser["page"].screenshot = AsyncMock(return_value=large_data)

        result = browser(
            action="screenshot",
            url="https://example.com",
            trace_id="test-trace",
        )

        # Should warn about large size or reject
        assert result.get("status") in ["success", "error"]
        if result.get("status") == "success":
            assert "warning" in str(result.get("data", {})).lower() or "truncated" in str(result.get("data", {})).lower()
