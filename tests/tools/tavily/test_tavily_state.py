"""Tavily tests — state ownership (regression guard for web bug)."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily_ops.client import _get_singleton_client
import tools.tavily_ops.state as state


class TestStateOwnership:
    """Verify state.py owns the variables client.py mutates.

    This test would have caught the web refactor bug where
    `from state import _HTTP_CLIENT` created a local name binding
    that diverged from state.py's actual variable.
    """

    def test_reset_state_actually_clears_singleton(self, mock_tavily_client):
        c1 = _get_singleton_client()
        state.reset_state()
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "different-key"):
            c2 = _get_singleton_client()
        assert c1 is not c2

    def test_reset_state_clears_keyless_warned(self, mock_tavily_client):
        import logging
        from tools.tavily import tavily
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            with patch("tools.tavily_ops.client.logger") as mock_logger:
                tavily(action="search", query="test")
                assert state._KEYLESS_WARNED is True
        state.reset_state()
        assert state._KEYLESS_WARNED is False
