"""Browser tool tests — facade behavior."""
from __future__ import annotations

import inspect
import typing
from unittest.mock import patch, AsyncMock

from tools.browser import browser
from tools.browser_ops._registry import DISPATCH


class TestFacade:
    """Test browser facade behavior."""

    def test_meta_tool_generates_literal(self):
        """browser() action parameter should be Literal[...] after @meta_tool."""
        ann = browser.__annotations__.get("action")
        assert ann is not None
        args = typing.get_args(ann)
        assert "navigate" in args
        assert "click" in args
        assert "close" in args
        assert "hover" in args
        assert "cookies" in args
        assert "extract_links" in args
        assert "extract_tables" in args
        assert "upload" in args  # NEW action

    def test_unknown_action(self, mock_browser):
        result = browser(action="dance", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_empty_action(self, mock_browser):
        result = browser(action="", trace_id="t1")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_tracer_steps_on_success(self, mock_browser):
        with patch("tools.browser.tracer.step") as mock_step:
            browser(action="get_url", trace_id="t1")
            calls = [c[0] for c in mock_step.call_args_list]
            assert any("action=get_url" in str(c) for c in calls)

    def test_screenshot_base64(self, mock_browser, tmp_path):
        with patch("tools.browser_ops.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            result = browser(
                action="screenshot", return_base64=True, trace_id="t1"
            )
            assert result["status"] == "success"
            assert "path" in result["data"]

    def test_screenshot_on_failure_skipped_for_screenshot_action(self, mock_browser):
        """If screenshot action itself raises, do not attempt failure screenshot."""
        mock_browser["page"].screenshot = AsyncMock(
            side_effect=Exception("Page crashed")
        )
        with patch("tools.browser._try_failure_screenshot") as mock_screenshot:
            result = browser(action="screenshot", trace_id="t1")
            assert result["status"] == "error"
            # _try_failure_screenshot should NOT be called for screenshot action
            mock_screenshot.assert_not_called()

    def test_screenshot_on_failure_skipped_for_close_action(self, mock_browser):
        """If close action fails, do not attempt failure screenshot."""
        # Patch DISPATCH directly — the facade looks up handler from DISPATCH at runtime
        original_close = DISPATCH["browser"]["close"]["func"]
        try:
            DISPATCH["browser"]["close"]["func"] = lambda **kwargs: (_ for _ in ()).throw(
                Exception("Forced close failure")
            )
            with patch("tools.browser._try_failure_screenshot") as mock_screenshot:
                result = browser(action="close", trace_id="t1")
                assert result["status"] == "error"
                mock_screenshot.assert_not_called()
        finally:
            DISPATCH["browser"]["close"]["func"] = original_close

    def test_screenshot_on_failure_called_for_other_actions(self, mock_browser):
        """Failure screenshot should be attempted for non-screenshot actions."""
        mock_browser["page"].click = AsyncMock(
            side_effect=Exception("Timeout")
        )
        with patch("tools.browser._try_failure_screenshot") as mock_screenshot:
            mock_screenshot.return_value = None
            result = browser(
                action="click", selector="button", trace_id="t1"
            )
            assert result["status"] == "error"
            mock_screenshot.assert_called_once_with("t1")
