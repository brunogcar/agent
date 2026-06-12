"""
tests/tools/browser/test_browser.py
Comprehensive tests for the Playwright browser tool.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from tools.browser import browser


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture(autouse=True)
def reset_browser_state():
    """Reset browser singleton state between tests."""
    import tools.browser

    tools.browser._browser = None
    tools.browser._playwright = None
    tools.browser._pages.clear()
    tools.browser._contexts.clear()
    tools.browser._reaper_started = False
    yield
    tools.browser._browser = None
    tools.browser._playwright = None
    tools.browser._pages.clear()
    tools.browser._contexts.clear()
    tools.browser._reaper_started = False


@pytest.fixture(autouse=True)
def mock_browser():
    """Mock browser internals by patching _launch_browser."""
    with patch("tools.browser._launch_browser", new_callable=AsyncMock) as mock_launch:
        # Build mock page with async methods for actions, sync for event handlers
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.click = AsyncMock(return_value=None)
        mock_page.fill = AsyncMock(return_value=None)
        mock_page.type = AsyncMock(return_value=None)
        mock_page.screenshot = AsyncMock(return_value=None)
        mock_page.text_content = AsyncMock(return_value="Page text content")
        mock_page.evaluate = AsyncMock(return_value="Evaluated result")
        mock_page.select_option = AsyncMock(return_value=None)
        mock_page.keyboard.press = AsyncMock(return_value=None)
        # on() is synchronous — just store the callback
        mock_page.on = MagicMock()

        # Mock element for selector-based screenshot
        mock_element = AsyncMock()
        mock_element.screenshot = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        # Build mock context
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock(return_value=None)

        # Build mock browser instance
        mock_browser_instance = AsyncMock()
        mock_browser_instance.new_context = AsyncMock(return_value=mock_context)
        mock_browser_instance.close = AsyncMock(return_value=None)

        # Patch _launch_browser to return mock browser instance
        mock_launch.return_value = mock_browser_instance

        yield {
            "launch": mock_launch,
            "page": mock_page,
            "context": mock_context,
            "browser": mock_browser_instance,
            "element": mock_element,
        }


# =============================================================================
# Test Navigate
# =============================================================================
class TestNavigate:
    def test_navigate_success(self, mock_browser):
        result = browser(action="navigate", url="https://example.com", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["title"] == "Test Page"

    def test_navigate_missing_url(self, mock_browser):
        result = browser(action="navigate", url="")
        assert result["status"] == "error"
        assert "url is required" in result["error"]

    def test_navigate_ssrf_blocks_private(self, mock_browser):
        result = browser(
            action="navigate", url="http://192.168.1.1/admin", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "SSRF" in result["error"]


# =============================================================================
# Test Click
# =============================================================================
class TestClick:
    def test_click_success(self, mock_browser):
        result = browser(action="click", selector="button.submit", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["clicked"] is True

    def test_click_missing_selector(self, mock_browser):
        result = browser(action="click", selector="", trace_id="t1")
        assert result["status"] == "error"
        assert "selector is required" in result["error"]


# =============================================================================
# Test Fill
# =============================================================================
class TestFill:
    def test_fill_success(self, mock_browser):
        result = browser(
            action="fill",
            selector="input.email",
            value="test@example.com",
            trace_id="t1",
        )
        assert result["status"] == "success"
        assert result["data"]["filled"] is True

    def test_fill_missing_params(self, mock_browser):
        result = browser(action="fill", selector="input", value=None, trace_id="t1")
        assert result["status"] == "error"
        assert "selector and value are required" in result["error"]


# =============================================================================
# Test Screenshot
# =============================================================================
class TestScreenshot:
    def test_screenshot_full_page(self, mock_browser, tmp_path):
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            result = browser(action="screenshot", trace_id="t1")
            assert result["status"] == "success"
            assert "path" in result["data"]

    def test_screenshot_with_selector(self, mock_browser, tmp_path):
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            result = browser(
                action="screenshot", selector="div.content", trace_id="t1"
            )
            assert result["status"] == "success"

    def test_screenshot_selector_not_found(self, mock_browser, tmp_path):
        with patch("tools.browser.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].query_selector.return_value = None
            result = browser(
                action="screenshot", selector="div.missing", trace_id="t1"
            )
            assert result["status"] == "error"
            assert "not found" in result["error"]


# =============================================================================
# Test Text Content
# =============================================================================
class TestTextContent:
    def test_text_content_default_body(self, mock_browser):
        result = browser(action="text_content", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["text"] == "Page text content"

    def test_text_content_custom_selector(self, mock_browser):
        result = browser(action="text_content", selector="div.main", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["selector"] == "div.main"


# =============================================================================
# Test Evaluate
# =============================================================================
class TestEvaluate:
    def test_evaluate_success(self, mock_browser):
        result = browser(
            action="evaluate", expression="document.title", trace_id="t1"
        )
        assert result["status"] == "success"
        assert result["data"]["result"] == "Evaluated result"

    def test_evaluate_missing_expression(self, mock_browser):
        result = browser(action="evaluate", expression="", trace_id="t1")
        assert result["status"] == "error"
        assert "expression is required" in result["error"]


# =============================================================================
# Test Close
# =============================================================================
class TestClose:
    def test_close_success(self, mock_browser):
        # First navigate to create context
        browser(action="navigate", url="https://example.com", trace_id="t1")
        result = browser(action="close", trace_id="t1")
        assert result["status"] == "success"
        assert result["data"]["closed"] is True


# =============================================================================
# Test Error Handling
# =============================================================================
class TestErrorHandling:
    def test_unknown_action(self, mock_browser):
        result = browser(action="unknown_action", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_playwright_error_cleanup(self, mock_browser):
        mock_browser["page"].goto.side_effect = Exception("Navigation failed")
        result = browser(
            action="navigate", url="https://example.com", trace_id="t1"
        )
        assert result["status"] == "error"
        assert "Navigation failed" in result["error"]
