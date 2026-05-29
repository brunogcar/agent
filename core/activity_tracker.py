"""
core/activity_tracker.py — Global activity and inference tracker.
Used by the Meta-Learning daemon to determine if the agent is idle.
"""
from __future__ import annotations

import threading
import time

class ActivityTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.last_user_activity = time.time()
        self.active_inferences = 0
        self.background_active = False

    def touch(self):
        """Call this on every user interaction."""
        with self._lock:
            self.last_user_activity = time.time()

    def inference_start(self):
        """Call before any LLM generation."""
        with self._lock:
            self.active_inferences += 1
            self.last_user_activity = time.time()

    def inference_end(self):
        """Call after LLM generation finishes."""
        with self._lock:
            if self.active_inferences > 0:
                self.active_inferences -= 1

    def try_acquire_background_slot(self, min_idle_seconds: int = 7200) -> bool:
        """Atomically check if idle and reserve the slot for background work."""
        with self._lock:
            if self.active_inferences > 0:
                return False
            if self.background_active:
                return False
            if (time.time() - self.last_user_activity) < min_idle_seconds:
                return False
            
            self.background_active = True
            self.active_inferences += 1
            return True

    def release_background_slot(self):
        """Release the background reservation."""
        with self._lock:
            self.background_active = False
            if self.active_inferences > 0:
                self.active_inferences -= 1

# Singleton
tracker = ActivityTracker()