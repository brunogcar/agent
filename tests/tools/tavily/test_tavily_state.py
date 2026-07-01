"""Tavily tests — state management.

v1.2: Fixed _KEYLESS_WARNED test.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tools.tavily_ops import state
from tools.tavily_ops.client import _close_client


class TestStateOwnership:
    """Test that singleton state is properly managed."""

    def test_reset_state_clears_client(self):
        state._TAVILY_CLIENT = "fake_client"
        state._TAVILY_CLIENT_KEY = "fake_key"
        state._reset_state()
        assert state._TAVILY_CLIENT is None
        assert state._TAVILY_CLIENT_KEY is None

    def test_reset_state_clears_keyless_warned(self):
        """v1.2 FIX: Set _KEYLESS_WARNED before checking it gets cleared."""
        from tools.tavily_ops import client as client_module
        client_module._KEYLESS_WARNED = True
        state._reset_state()
        assert client_module._KEYLESS_WARNED is False

    def test_close_client_is_idempotent(self):
        state._TAVILY_CLIENT = None
        state._TAVILY_CLIENT_KEY = None
        _close_client()
        assert state._TAVILY_CLIENT is None
        assert state._TAVILY_CLIENT_KEY is None
