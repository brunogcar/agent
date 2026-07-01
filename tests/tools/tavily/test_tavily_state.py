"""Tests for tools/tavily_ops/state.py — module state ownership.

v1.3: Fixed to use reset_state() (no underscore prefix).
      Added _reset_state alias for backward compatibility.
      FIXED: Tests now verify state._KEYLESS_WARNED (the canonical location)
      since client.py v1.3 uses state._KEYLESS_WARNED.
"""
from __future__ import annotations

import pytest

from tools.tavily_ops import state


class TestStateOwnership:
    """Tests verifying state module owns tavily client lifecycle state."""

    def test_reset_state_clears_client(self):
        state._TAVILY_CLIENT = "fake_client"
        state._TAVILY_CLIENT_KEY = "fake_key"
        state.reset_state()
        assert state._TAVILY_CLIENT is None
        assert state._TAVILY_CLIENT_KEY is None

    def test_reset_state_clears_keyless_warned(self):
        """v1.3 FIX: client.py now uses state._KEYLESS_WARNED directly."""
        state._KEYLESS_WARNED = True
        state.reset_state()
        assert state._KEYLESS_WARNED is False

    def test_reset_state_idempotent(self):
        state.reset_state()
        state.reset_state()
        assert state._TAVILY_CLIENT is None
        assert state._TAVILY_CLIENT_KEY is None
        assert state._KEYLESS_WARNED is False
