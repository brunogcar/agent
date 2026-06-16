"""Browser tool tests — error handling.

All browser infrastructure is fully mocked; no real Chromium is launched.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from tools.browser import browser


# ── Shared fixtures (each file is self-contained) ───────────────────────────

@pytest.fixture(autouse=True)
def reset_browser_state():
    """Reset all browser module globals before each test."""
    from tools import browser as browser_mod
    browser_mod._browser = None
    browser_mod._playwright = None
    browser_mod._contexts.clear()
    browser_mod._pages.clear()
    browser_mod._reaper_started = False
    browser_mod._browser_loop = None
    browser_mod._browser_thread = None
    yield
    browser_mod._contexts.clear()
    browser_mod._pages.clear()
    browser_mod._browser = None
    browser_mod._playwright = None
    browser_mod._browser_loop = None
    browser_mod._browser_thread = None


@pytest.fixture(autouse=True)
def mock_cfg_for_browser(tmp_path):
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


class TestErrorHandling:
    """Test browser error handling."""

    def test_unknown_action(self, mock_browser):
        result = browser(action="dance", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
