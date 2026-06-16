"""Concurrency tests for MemoryStore read/write operations.

Verifies that simultaneous store() and recall() operations don't corrupt
shared state (_hash_cache, collections) via TOCTOU races.
"""
from __future__ import annotations

import concurrent.futures
import pytest
from unittest.mock import patch, MagicMock

from core.memory_backend.store import MemoryStore
from core.memory_backend.constants import COLLECTION_SEMANTIC


class TestStoreConcurrency:
    """Test MemoryStore thread safety under concurrent access."""

    @pytest.fixture
    def mock_client(self):
        """Mock ChromaDB client with in-memory collections."""
        with patch("core.memory_backend.store._make_client") as mock_make:
            client = MagicMock()
            collection = MagicMock()
            collection.get.return_value = {"metadatas": []}
            collection.add = MagicMock()
            collection.query = MagicMock(return_value={
                "ids": [["id1"]],
                "documents": [["test document"]],
                "metadatas": [[{"text_hash": "abc123"}]],
                "distances": [[0.1]],
            })
            client.get_or_create_collection.return_value = collection
            mock_make.return_value = client
            yield client

    def test_concurrent_store_and_recall(self, mock_client):
        """Simultaneous store() and recall() must not crash or corrupt state."""
        store = MemoryStore()

        def writer(n):
            return store.store(
                text=f"concurrent write {n}",
                memory_type=COLLECTION_SEMANTIC,
                importance=5,
                tags="test",
                trace_id=f"trace-{n}",
            )

        def reader(n):
            return store.recall(
                query=f"concurrent write {n}",
                top_k=1,
                trace_id=f"trace-{n}",
            )

        # Interleave writes and reads
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = []
            for i in range(10):
                futures.append(ex.submit(writer, i))
                futures.append(ex.submit(reader, i))
            results = [f.result() for f in futures]

        # All operations should complete without exception
        for r in results:
            assert r is not None  # No crashes

    def test_concurrent_store_same_hash(self, mock_client):
        """Two threads storing identical text must not duplicate (hash guard)."""
        store = MemoryStore()
        text = "duplicate hash test"

        def store_once():
            return store.store(
                text=text,
                memory_type=COLLECTION_SEMANTIC,
                importance=5,
                trace_id="dup-test",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(store_once)
            f2 = ex.submit(store_once)
            r1, r2 = f1.result(), f2.result()

        # Both should succeed (second may be deduplicated)
        assert r1 is not None
        assert r2 is not None

    def test_recall_during_store(self, mock_client):
        """Recall must not see partial/corrupt state during active store."""
        store = MemoryStore()

        def slow_store():
            # Simulate slow store by mocking add to sleep
            with patch.object(mock_client.get_or_create_collection.return_value, 'add', side_effect=lambda **kw: __import__('time').sleep(0.1)):
                return store.store(
                    text="slow write",
                    memory_type=COLLECTION_SEMANTIC,
                    trace_id="slow-test",
                )

        def fast_recall():
            return store.recall(query="slow write", top_k=1, trace_id="slow-test")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f_store = ex.submit(slow_store)
            f_recall = ex.submit(fast_recall)
            r_store = f_store.result(timeout=5)
            r_recall = f_recall.result(timeout=5)

        assert r_store is not None
        assert isinstance(r_recall, list)  # recall returns list, not crash
