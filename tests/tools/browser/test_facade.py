"""Browser tool tests — facade behavior."""
from __future__ import annotations

import inspect
import typing
from unittest.mock import patch, AsyncMock

from tools.browser import browser


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
        with patch("tools.browser_core.actions.screenshot.cfg") as mock_cfg:
            mock_cfg.workspace_root = tmp_path
            mock_browser["page"].screenshot = AsyncMock(return_value=None)
            result = browser(action="screenshot", return_base64=True, trace_id="t1")
            assert result["status"] == "success"
            assert "path" in result["data"]
