"""Browser tool tests — close action."""
from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock
from tools.browser import browser
from tools.browser_core.state import _contexts, _pages


class TestClose:
    """Test browser close action."""

    def test_close_with_trace_id(self, mock_browser):
        """Close with trace_id should find and close the context."""
        # Pre-populate _contexts so close has something to close
        mock_ctx = MagicMock()
        mock_ctx.close = AsyncMock(return_value=None)
        _contexts["t1"] = (mock_ctx, 0.0)
        _pages["t1"] = mock_browser["page"]
        try:
            result = browser(action="close", trace_id="t1")
            assert result["status"] == "success"
            assert result["data"]["closed"] is True
            mock_ctx.close.assert_called_once()
        finally:
            _contexts.pop("t1", None)
            _pages.pop("t1", None)

    def test_close_without_trace_id(self, mock_browser):
        """close() without trace_id must return an error, not silently succeed."""
        result = browser(action="close")
        assert result["status"] == "error"
        assert "trace_id is required" in result["error"]

    def test_close_unknown_trace_id(self, mock_browser):
        """Closing a non-existent trace returns closed: False with reason."""
        result = browser(action="close", trace_id="unknown_trace")
        assert result["status"] == "success"
        assert result["data"]["closed"] is False
        assert "context not found" in result["data"]["reason"]
