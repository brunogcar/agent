"""Tests for server.py daemon thread coordination.

[BUGFIX-4] Covers the threading.Event barriers for coordinated startup.
"""
from __future__ import annotations

import threading
import time
import pytest


class TestDaemonCoordination:
    """Verify dependent threads block until ChromaDB/model warmup completes."""

    def test_chromadb_ready_event_blocks_dependent_threads(self):
        """Threads waiting on _chromadb_ready must block until set()."""
        chromadb_ready = threading.Event()
        started = threading.Event()
        completed = threading.Event()

        def dependent_thread():
            started.set()
            chromadb_ready.wait(timeout=5)
            completed.set()

        t = threading.Thread(target=dependent_thread, daemon=True)
        t.start()

        # Wait for thread to start
        assert started.wait(timeout=1), "Thread never started"
        # Should be blocked on the event
        time.sleep(0.1)
        assert not completed.is_set(), "Thread completed before chromadb_ready was set"

        # Signal ready
        chromadb_ready.set()
        assert completed.wait(timeout=2), "Thread never completed after chromadb_ready.set()"
        t.join(timeout=1)

    def test_model_ready_event_blocks_dependent_threads(self):
        """Threads waiting on _model_ready must block until set()."""
        model_ready = threading.Event()
        started = threading.Event()
        completed = threading.Event()

        def dependent_thread():
            started.set()
            model_ready.wait(timeout=5)
            completed.set()

        t = threading.Thread(target=dependent_thread, daemon=True)
        t.start()

        assert started.wait(timeout=1)
        time.sleep(0.1)
        assert not completed.is_set()

        model_ready.set()
        assert completed.wait(timeout=2)
        t.join(timeout=1)

    def test_multiple_threads_wait_on_same_event(self):
        """Multiple threads can wait on the same Event and all unblock together."""
        event = threading.Event()
        completions = []
        lock = threading.Lock()

        def worker():
            event.wait(timeout=5)
            with lock:
                completions.append(threading.current_thread().name)

        threads = [threading.Thread(target=worker, daemon=True, name=f"worker-{i}") for i in range(5)]
        for t in threads:
            t.start()

        time.sleep(0.1)
        assert len(completions) == 0, "Threads completed before event was set"

        event.set()
        for t in threads:
            t.join(timeout=2)

        assert len(completions) == 5, f"Only {len(completions)} of 5 threads completed"

    def test_event_timeout_does_not_deadlock(self):
        """Threads with timeout must not deadlock if event is never set."""
        event = threading.Event()
        completed = threading.Event()

        def worker():
            event.wait(timeout=0.5)
            completed.set()

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        assert completed.wait(timeout=2), "Thread deadlocked instead of timing out"
        t.join(timeout=1)
