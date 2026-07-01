"""Tests for tools/tavily_ops/client.py — client lifecycle.

v1.3: Fixed test_close_client_acquires_lock to actually verify lock acquisition.
      FIXED: api_key attribute tests now check _is_keyless_mode() instead of
      non-existent AsyncTavilyClient.api_key attribute.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from tools.tavily_ops.client import (
    _get_singleton_client,
    _close_client,
    _is_keyless_mode,
)
from tools.tavily_ops import state


class TestClientLifecycle:
    """Tests for Tavily client singleton lifecycle."""

    def test_singleton_returns_same_instance(self):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "test-key"):
            client1 = _get_singleton_client()
            client2 = _get_singleton_client()
            assert client1 is client2

    def test_key_change_creates_new_client(self):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "key-a"):
            client_a = _get_singleton_client()
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "key-b"):
            client_b = _get_singleton_client()
        assert client_a is not client_b

    def test_keyless_mode_empty_string(self):
        """v1.3 FIX: Check keyless mode detection instead of non-existent api_key attr."""
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", ""):
            _get_singleton_client()
            assert _is_keyless_mode() is True

    def test_keyless_mode_none(self):
        """v1.3 FIX: Check keyless mode detection instead of non-existent api_key attr."""
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", None):
            _get_singleton_client()
            assert _is_keyless_mode() is True

    def test_close_client_clears_state(self):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "test-key"):
            _get_singleton_client()
            _close_client()
            assert state._TAVILY_CLIENT is None
            assert state._TAVILY_CLIENT_KEY is None

    def test_close_client_logs_on_failure(self, caplog):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "test-key"):
            _get_singleton_client()
        with patch.object(state._TAVILY_CLIENT, "close", side_effect=RuntimeError("boom")):
            _close_client()
        assert "Failed to close Tavily client" in caplog.text

    def test_close_client_acquires_lock(self):
        """Verify _close_client acquires _CLIENT_LOCK.

        v1.3: Actually tests lock acquisition using a threading event.
        v1.3 FIX: Ensure client exists before patching close method.
        """
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "test-key"):
            _get_singleton_client()

        lock_held = threading.Event()
        original_close = state._TAVILY_CLIENT.close

        def instrumented_close(*args, **kwargs):
            if state._CLIENT_LOCK.locked():
                lock_held.set()
            return original_close(*args, **kwargs)

        state._TAVILY_CLIENT.close = instrumented_close
        try:
            _close_client()
            assert lock_held.is_set(), "Lock was not held during close"
        finally:
            # v1.3 FIX: Only restore if client still exists (may be None after close)
            if state._TAVILY_CLIENT is not None:
                state._TAVILY_CLIENT.close = original_close

    def test_key_change_closes_old_client(self):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "old-key"):
            old_client = _get_singleton_client()
        with patch.object(old_client, "close") as mock_close:
            with patch("tools.tavily_ops.client.cfg.tavily_api_key", "new-key"):
                _get_singleton_client()
            mock_close.assert_called_once()
