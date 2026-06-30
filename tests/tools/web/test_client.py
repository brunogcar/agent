"""Unit tests for httpx.Client singleton and connection pooling."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestSingletonClient:
    def test_singleton_returns_same_instance(self):
        from tools.web_ops.client import _get_singleton_client
        c1 = _get_singleton_client()
        c2 = _get_singleton_client()
        assert c1 is c2

    def test_singleton_has_connection_limits(self):
        from tools.web_ops.client import _get_singleton_client
        client = _get_singleton_client()
        assert client._transport._pool._max_connections == 20

    def test_make_client_returns_context_manager(self):
        from tools.web_ops.client import _make_client
        ctx = _make_client()
        assert hasattr(ctx, '__enter__')
        assert hasattr(ctx, '__exit__')

    def test_make_client_yields_singleton(self):
        from tools.web_ops.client import _make_client, _get_singleton_client
        with _make_client() as client:
            assert client is _get_singleton_client()

    def test_singleton_thread_safe(self):
        import threading
        from tools.web_ops.client import _get_singleton_client
        clients = []
        lock = threading.Lock()
        def fetch():
            c = _get_singleton_client()
            with lock:
                clients.append(c)
        threads = [threading.Thread(target=fetch) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(id(c) for c in clients)) == 1

    def test_close_client_resets_singleton(self):
        """_close_client must set the singleton to None."""
        from tools.web_ops.client import _close_client
        import tools.web_ops.state as state_module
        # Just verify that calling _close_client() sets _HTTP_CLIENT to None
        _close_client()
        assert state_module._HTTP_CLIENT is None
