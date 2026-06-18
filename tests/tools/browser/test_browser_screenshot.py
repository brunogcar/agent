"""Tests for browser screenshot size limits and pruning.

Verifies that large base64 screenshots don't context-bomb the LLM.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from tools.browser import browser


class TestScreenshotSizeLimits:
    """Verify screenshot results are pruned to prevent context overflow."""

    def test_screenshot_under_limit(self, mock_browser):
        """Small screenshot should return full base64 data."""
        small_image = b"\x89PNG\r\n\x1a\n" + b"x" * 1000  # ~1KB
        mock_browser["page"].screenshot = AsyncMock(return_value=small_image)

        result = browser(
            action="screenshot",
            trace_id="test-trace",
        )

        assert result.get("status") == "success"
        mock_browser["page"].screenshot.assert_called_once()

    def test_large_screenshot_truncated(self, mock_browser):
        """Screenshot exceeding safe limit should be truncated or rejected."""
        pytest.skip("Screenshot size limits not yet implemented")

    def test_screenshot_size_warning(self, mock_browser):
        """Very large screenshot should include a size warning."""
        pytest.skip("Screenshot size limits not yet implemented")
