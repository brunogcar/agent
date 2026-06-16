"""Unit tests for httpx.Client singleton and connection pooling.

[BUGFIX-6] Covers the module-level singleton httpx.Client with connection pooling.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestSingletonClient:
    """Verify singleton client behavior and pooling."""

    def test_singleton_returns_same_instance(self):
        """Multiple calls to _get_singleton_client return the same object."""
        from tools.web import _get_singleton_client
        c1 = _get_singleton_client()
        c2 = _get_singleton_client()
        assert c1 is c2, "Singleton client should return the same instance"

    def test_singleton_has_connection_limits(self):
        """Singleton client must have Limits configured for pooling."""
        from tools.web import _get_singleton_client
        client = _get_singleton_client()
        # httpx stores limits in _transport._pool._max_connections
        assert hasattr(client, '_transport')
        assert hasattr(client._transport, '_pool')
        assert hasattr(client._transport._pool, '_max_connections')
        assert client._transport._pool._max_connections == 20

    def test_make_client_returns_context_manager(self):
        """_make_client() returns a context manager compatible with 'with'."""
        from tools.web import _make_client
        ctx = _make_client()
        assert hasattr(ctx, '__enter__')
        assert hasattr(ctx, '__exit__')

    def test_make_client_yields_singleton(self):
        """Context manager from _make_client yields the singleton instance."""
        from tools.web import _make_client, _get_singleton_client
        with _make_client() as client:
            assert client is _get_singleton_client()

    def test_singleton_thread_safe(self):
        """Singleton creation must be thread-safe under concurrent access."""
        import threading
        from tools.web import _get_singleton_client

        clients = []
        lock = threading.Lock()

        def fetch():
            c = _get_singleton_client()
            with lock:
                clients.append(c)

        threads = [threading.Thread(target=fetch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the exact same instance
        assert len(set(id(c) for c in clients)) == 1

    def test_close_client_resets_singleton(self):
        """_close_client must reset the singleton to None."""
        from tools.web import _get_singleton_client, _close_client, _HTTP_CLIENT
        # Ensure singleton exists
        _get_singleton_client()
        assert _HTTP_CLIENT is not None
        _close_client()
        from tools.web import _HTTP_CLIENT as client_after
        assert client_after is None
