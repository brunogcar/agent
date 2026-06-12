"""
❌ tests/tools/browser/test_browser.py — Browser tool unit tests (fully mocked).

Strategy: Patch _launch_browser so no real Chromium is launched.
All actions are tested against mocked Page / BrowserContext objects.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from tools.browser import browser


# ── Fixtures ───────────────────────────────────────────────────────────────

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
    # Cleanup after test
    browser_mod._contexts.clear()
    browser_mod._pages.clear()
    browser_mod._browser = None
    browser_mod._playwright = None
    browser_mod._browser_loop = None
    browser_mod._browser_thread = None


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


# ── Test: Navigate ─────────────────────────────────────────────────────────

class TestNavigate:
    def test_navigate_success(self, mock_browser):
        result = browser(action="navigate", url="https://example.com", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["title"] == "Example Page"
        mock_browser["page"].goto.assert_called_once()

    def test_navigate_missing_url(self, mock_browser):
        result = browser(action="navigate", trace_id="t1")
        assert result["status"] == "error"
        assert "url is required" in result["error"]

    def test_navigate_ssrf_blocked(self, mock_browser):
        with patch("tools.browser.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://127.0.0.1/admin", trace_id="t1")
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_timeout(self, mock_browser):
        mock_browser["page"].goto.side_effect = Exception("Timeout")
        result = browser(action="navigate", url="https://example.com", trace_id="t1", timeout=1)
        assert result["status"] == "error"
        assert "Navigation failed" in result["error"]


# ── Test: Click ──────────────────────────────────────────────────────────────

class TestClick:
    def test_click_success(self, mock_browser):
        result = browser(action="click", selector="button.submit", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["clicked"] is True
        mock_browser["page"].click.assert_called_once_with("button.submit", timeout=30000)

    def test_click_missing_selector(self, mock_browser):
        result = browser(action="click", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]


# ── Test: Fill ───────────────────────────────────────────────────────────────

class TestFill:
    def test_fill_success(self, mock_browser):
        result = browser(action="fill", selector="input.email", value="test@test.com", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["filled"] is True
        mock_browser["page"].fill.assert_called_once_with("input.email", "test@test.com", timeout=30000)

    def test_fill_missing_selector(self, mock_browser):
        result = browser(action="fill", value="test", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]


# ── Test: Type ───────────────────────────────────────────────────────────────

class TestType:
    def test_type_success(self, mock_browser):
        result = browser(action="type", selector="input.search", value="hello", delay=100, trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["typed"] is True
        mock_browser["page"].type.assert_called_once_with("input.search", "hello", delay=100, timeout=30000)

    def test_type_missing_selector(self, mock_browser):
        result = browser(action="type", value="hello", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]


# ── Test: Screenshot ─────────────────────────────────────────────────────────

class TestScreenshot:
    def test_screenshot_full_page(self, mock_browser, tmp_path):
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            result = browser(action="screenshot", trace_id="t1")
            assert result["status"] == "success"
            assert "path" in result["data"]
            mock_browser["page"].screenshot.assert_called_once()

    def test_screenshot_element(self, mock_browser, tmp_path):
        mock_el = MagicMock()
        mock_el.screenshot = AsyncMock(return_value=None)
        mock_browser["page"].query_selector = AsyncMock(return_value=mock_el)
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            result = browser(action="screenshot", selector="#chart", trace_id="t1")
            assert result["status"] == "success"
            mock_el.screenshot.assert_called_once()

    def test_screenshot_element_not_found(self, mock_browser, tmp_path):
        mock_browser["page"].query_selector = AsyncMock(return_value=None)
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            result = browser(action="screenshot", selector="#missing", trace_id="t1")
            assert result["status"] == "error"
            assert "Element not found" in result["error"]


# ── Test: Text Content ───────────────────────────────────────────────────────

class TestTextContent:
    def test_text_content_success(self, mock_browser):
        result = browser(action="text_content", selector="article", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["text"] == "Hello World"
        mock_browser["page"].text_content.assert_called_once_with("article", timeout=30000)

    def test_text_content_default_body(self, mock_browser):
        result = browser(action="text_content", trace_id="t1")
        assert result["status"] == "success"
        mock_browser["page"].text_content.assert_called_once_with("body", timeout=30000)


# ── Test: Evaluate ───────────────────────────────────────────────────────────

class TestEvaluate:
    def test_evaluate_success(self, mock_browser):
        result = browser(action="evaluate", expression="document.title", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["result"] == "eval_result"
        mock_browser["page"].evaluate.assert_called_once_with("document.title")

    def test_evaluate_missing_expression(self, mock_browser):
        result = browser(action="evaluate", trace_id="t1")
        assert result["status"] == "error"
        assert "expression is required" in result["error"]


# ── Test: Select Option ──────────────────────────────────────────────────────

class TestSelectOption:
    def test_select_option_success(self, mock_browser):
        result = browser(action="select_option", selector="select#country", value="US", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["selected"] == "US"
        mock_browser["page"].select_option.assert_called_once_with("select#country", "US", timeout=30000)

    def test_select_option_missing_selector(self, mock_browser):
        result = browser(action="select_option", value="US", trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]


# ── Test: Keyboard Press ─────────────────────────────────────────────────────

class TestKeyboardPress:
    def test_keyboard_press_success(self, mock_browser):
        result = browser(action="keyboard_press", key="Enter", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["pressed"] == "Enter"
        mock_browser["page"].keyboard.press.assert_called_once_with("Enter")

    def test_keyboard_press_missing_key(self, mock_browser):
        result = browser(action="keyboard_press", trace_id="t1")
        assert result["status"] == "error"
        assert "key is required" in result["error"]


# ── Test: Get URL ────────────────────────────────────────────────────────────

class TestGetUrl:
    def test_get_url_success(self, mock_browser):
        result = browser(action="get_url", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"


# ── Test: Close ──────────────────────────────────────────────────────────────

class TestClose:
    def test_close_success(self, mock_browser):
        # First navigate to create a page
        browser(action="navigate", url="https://example.com", trace_id="t1")
        result = browser(action="close", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["closed"] is True

    def test_close_no_context(self, mock_browser):
        result = browser(action="close", trace_id="nonexistent")
        assert result["status"] == "success"  # Graceful no-op


# ── Test: Error Handling ─────────────────────────────────────────────────────

class TestErrorHandling:
    def test_unknown_action(self, mock_browser):
        result = browser(action="dance", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]


# ── Test: SSRF ───────────────────────────────────────────────────────────────

class TestSSRF:
    def test_navigate_private_ip(self, mock_browser):
        with patch("tools.browser.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://192.168.1.1", trace_id="t1")
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_localhost(self, mock_browser):
        with patch("tools.browser.is_safe_network_address", return_value=False):
            result = browser(action="navigate", url="http://localhost:8080", trace_id="t1")
            assert result["status"] == "error"
            assert "SSRF blocked" in result["error"]

    def test_navigate_public_allowed(self, mock_browser):
        result = browser(action="navigate", url="https://github.com", trace_id="t1")
        assert result["status"] == "success"
