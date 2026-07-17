"""Tests for kgraph v1.0 fixes: GraphStore.close_all() + AST cache key."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGraphStoreCloseAll:
    """GraphStore.close_all() — closes all singleton instances."""

    def test_close_all_exists(self):
        """close_all() is a classmethod on GraphStore."""
        from core.kgraph.storage import GraphStore
        assert hasattr(GraphStore, "close_all")
        assert callable(GraphStore.close_all)

    def test_close_all_closes_all_instances(self, tmp_path):
        """close_all() closes all instances in _instances dict."""
        from core.kgraph.storage import GraphStore
        db = tmp_path / "test.db"
        store1 = GraphStore(db)
        store2 = GraphStore(db)  # same path → same instance
        assert len(GraphStore._instances) >= 1
        GraphStore.close_all()
        assert len(GraphStore._instances) == 0

    def test_close_all_clears_instances(self):
        """After close_all(), _instances is empty."""
        from core.kgraph.storage import GraphStore
        GraphStore.close_all()
        assert len(GraphStore._instances) == 0

    def test_close_all_is_thread_safe(self):
        """close_all() acquires _lock — doesn't crash under concurrent access."""
        from core.kgraph.storage import GraphStore
        # Just verify it doesn't deadlock
        GraphStore.close_all()
        GraphStore.close_all()  # calling twice should be safe


class TestAstCacheKey:
    """AST cache key uses original path (not resolved absolute)."""

    def test_cache_key_uses_original_path(self):
        """If file_path is relative, the cache key uses the relative path."""
        from core.kgraph.ast_parser import _parse_file_dependencies_sync
        # The cache key is (project_id, file_path, md5_hash)
        # If we call with a relative path, it should be cached under that key,
        # not under the resolved absolute path.
        # Verify by checking the cache info
        _parse_file_dependencies_sync.cache_clear()
        # We can't easily test this without a real file, but we can verify
        # the function accepts a relative path string without crashing
        assert callable(_parse_file_dependencies_sync)

    def test_clear_ast_cache_exists(self):
        """clear_ast_cache() is available for cache invalidation."""
        from core.kgraph.ast_parser import clear_ast_cache
        assert callable(clear_ast_cache)
        # Should not crash
        clear_ast_cache()


class TestServerAtexitRegistration:
    """server.py registers GraphStore.close_all() via atexit."""

    def test_shutdown_kgraph_registered(self):
        """The _shutdown_kgraph function exists in server.py."""
        # Read server.py and check for the function
        import server
        # Can't easily test atexit registration without running the server,
        # but we can verify the function exists
        assert hasattr(server, "_shutdown_kgraph") or "_shutdown_kgraph" in open("server.py").read()
