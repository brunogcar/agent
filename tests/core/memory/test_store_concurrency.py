"""Concurrency tests for MemoryStore read/write operations.

Verifies that simultaneous store() and recall() operations don't corrupt
shared state (hash_cache, collections) via TOCTOU races.
"""
from __future__ import annotations

import concurrent.futures
import pytest
from unittest.mock import patch, MagicMock

from core.memory_backend.store import MemoryStore
from core.memory_backend.constants import COLLECTION_SEMANTIC


class TestStoreConcurrencyMock:
    """Test MemoryStore thread safety with mocked ChromaDB client."""

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
        # The hash guard should prevent duplicate ChromaDB inserts.
        # collection.add should be called at most once for the same hash.
        collection = mock_client.get_or_create_collection.return_value
        assert collection.add.call_count <= 1, (
            f"Expected at most 1 add() call for duplicate hash, got {collection.add.call_count}. "
            "Hash deduplication may have a TOCTOU race."
        )

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


class TestStoreConcurrencyReal:
    """Integration test with real ChromaDB EphemeralClient.

    This test verifies that MemoryStore's locking and hash deduplication
    actually work against a real SQLite-backed ChromaDB, not just mocks.
    Mocks can't catch real database race conditions (e.g., SQLite
    'database is locked' errors under concurrent writes).

    Skipped if chromadb is not installed or EphemeralClient fails.
    """

    @pytest.fixture
    def real_store(self):
        """Create a MemoryStore backed by a real in-memory ChromaDB."""
        pytest.importorskip("chromadb", reason="chromadb not installed")
        try:
            import chromadb
            client = chromadb.EphemeralClient()
            store = MemoryStore.__new__(MemoryStore)
            store._client = client
            store._collections = {}
            store._hash_cache = set()
            store._write_lock = __import__('threading').Lock()
            # Initialize collections
            from core.memory_backend.constants import COLLECTION_SEMANTIC, COLLECTION_EPISODIC
            store._get_collection(COLLECTION_SEMANTIC)
            store._get_collection(COLLECTION_EPISODIC)
            yield store
        except Exception as e:
            pytest.skip(f"EphemeralClient failed: {e}")

    def test_real_concurrent_store_dedup(self, real_store):
        """Real ChromaDB: concurrent stores of same text must deduplicate."""
        text = "real concurrent dedup test"
        results = []

        def store_once():
            return real_store.store(
                text=text,
                memory_type=COLLECTION_SEMANTIC,
                importance=5,
                trace_id="real-dedup",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(store_once) for _ in range(10)]
            results = [f.result(timeout=10) for f in futures]

        # All should succeed
        assert all(r is not None for r in results)

        # Verify only one document exists in the collection
        collection = real_store._get_collection(COLLECTION_SEMANTIC)
        all_docs = collection.get()
        # Filter to our test text (may have other docs from previous tests)
        matching = [d for d in all_docs.get("documents", []) if d == text]
        assert len(matching) == 1, (
            f"Expected exactly 1 document for deduplicated text, found {len(matching)}. "
            "Hash deduplication failed under real concurrent load."
        )
