"""Tavily tests — client lifecycle and caching."""
from __future__ import annotations

import threading
import pytest
from unittest.mock import patch, MagicMock

from tools.tavily_ops.client import _get_singleton_client
import tools.tavily_ops.state as state


class TestClientCaching:
    """Test Tavily client singleton and key-change behavior."""

    def test_client_singleton(self, mock_tavily_client):
        c1 = _get_singleton_client()
        c2 = _get_singleton_client()
        assert c1 is c2

    def test_client_key_change(self, mock_tavily_client):
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "key-a"):
            c1 = _get_singleton_client()
        with patch("tools.tavily_ops.client.cfg.tavily_api_key", "key-b"):
            c2 = _get_singleton_client()
        assert c1 is not c2

    def test_client_thread_safety(self, mock_tavily_client):
        clients = []

        def get_client_thread():
            clients.append(_get_singleton_client())

        threads = [threading.Thread(target=get_client_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(c is clients[0] for c in clients)
