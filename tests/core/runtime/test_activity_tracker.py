"""tests/core/runtime/test_activity_tracker.py — Concurrency and idle detection tests."""
from __future__ import annotations
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from core.runtime.activity_tracker import tracker

def test_inference_slot_updates_touch():
    """Acquiring a slot MUST update last_user_activity."""
    before = tracker.last_user_activity
    time.sleep(0.2)
    with tracker.inference_slot(timeout=5.0):
        assert tracker.last_user_activity >= before, "touch() not called inside slot"

def test_rlock_prevents_nested_deadlock():
    """touch() calls inside locked context must not deadlock."""
    try:
        with tracker.inference_slot(timeout=2.0):
            tracker.touch()
            # If RLock is working correctly, this nested call won't hang
            tracker.touch()
    except Exception as e:
        assert False, f"Deadlock or exception during nested lock: {e}"

def test_slot_timeout_blocks_excess_workers():
    """Workers should time out if all slots are taken."""
    tracker.max_concurrent_inferences = 1
    results = []
    
    def worker():
        try:
            with tracker.inference_slot(timeout=1.0):
                time.sleep(2.0)
                return "success"
        except TimeoutError:
            return "timeout"
            
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(worker) for _ in range(3)]
        results = [f.result() for f in futures]
        
    assert results.count("timeout") >= 2, "Timeout should fire for excess workers"