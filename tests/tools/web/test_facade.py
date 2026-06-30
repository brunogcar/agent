"""Web tool tests — facade behavior."""
from __future__ import annotations

import typing
from unittest.mock import patch

from tools.web import web
from tools.web_ops._registry import DISPATCH


class TestFacade:
    """Test web facade behavior."""

    def test_meta_tool_generates_literal(self):
        """web() action parameter should be Literal[...] after @meta_tool."""
        ann = web.__annotations__.get("action")
        assert ann is not None
        args = typing.get_args(ann)
        assert "search" in args
        assert "scrape" in args
        assert "read" in args
        assert "search_and_read" in args

    def test_unknown_action(self, mock_cfg_for_web):
        result = web(action="dance")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_empty_action(self, mock_cfg_for_web):
        result = web(action="")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_tracer_steps_on_success(self, mock_cfg_for_web, mock_httpx):
        """Verify tracer.step is called on successful action."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        with patch("tools.web.tracer.step") as mock_step:
            web(action="search", query="test")
            calls = [c[0] for c in mock_step.call_args_list]
            assert any("action=search" in str(c) for c in calls)

    def test_tracer_steps_on_error(self, mock_cfg_for_web):
        """Verify tracer.step is called on unknown action error."""
        with patch("tools.web.tracer.step") as mock_step:
            web(action="nonsense")
            calls = [c[0] for c in mock_step.call_args_list]
            assert any("action=nonsense" in str(c) for c in calls)

    def test_max_chars_none_not_passed_to_handler(self, mock_cfg_for_web, mock_httpx):
        """When max_chars is omitted, the facade should NOT include it in kwargs.

        This verifies the fix for the max_chars=0 sentinel bug: handlers
        resolve cfg.web_max_text_chars when max_chars is absent.
        """
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        # Patch the handler function inside the DISPATCH registry entry.
        # The facade looks up handler = DISPATCH["web"]["search"]["func"]
        # and calls it directly, so we patch the func attribute.
        original_handler = DISPATCH["web"]["search"]["func"]
        mock_handler = MagicMock(return_value={"status": "success", "data": {}})
        try:
            DISPATCH["web"]["search"]["func"] = mock_handler
            web(action="search", query="test")
            assert mock_handler.called
            call_kwargs = mock_handler.call_args[1]  # kwargs dict
            assert "max_chars" not in call_kwargs
        finally:
            DISPATCH["web"]["search"]["func"] = original_handler
