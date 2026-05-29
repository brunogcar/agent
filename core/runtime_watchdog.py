"""
core/runtime_watchdog.py — LM Studio Process Watchdog.
Monitors LM Studio health via HTTP probe and automatically restarts
the process if it becomes unresponsive. Windows-native.
"""
from __future__ import annotations

import os
import sys
import time
import httpx
import subprocess
import threading
import logging
from pathlib import Path

from core.config import cfg
from core.runtime_providers import get_provider

logger = logging.getLogger(__name__)

LOCK_FILE = cfg.workspace_root / ".watchdog_restart.lock"
MAX_RESTARTS = 3
COOLDOWN_SECONDS = 15 * 60  # 15 minutes
CHECK_INTERVAL = 30         # 30 seconds
FAILURE_THRESHOLD = 3

class RuntimeWatchdog:
    def __init__(self):
        self._lock = threading.Lock()
        self.failure_count = 0
        self.restart_timestamps: list[float] = []
        self.provider = get_provider(cfg.runtime_provider)
        
    def run_forever(self):
        logger.info("[Watchdog] Daemon started.")
        while True:
            try:
                time.sleep(CHECK_INTERVAL)
                self._check_health()
            except Exception as e:
                logger.error(f"[Watchdog] Loop error: {e}")
                time.sleep(60)
                
    def _check_health(self):
        try:
            # Timeout aggressively (3s)
            resp = httpx.get(self.provider.health_url, timeout=3.0)
            if resp.status_code == 200:
                # Verify model backend is actually loaded (provider-specific)
                try:
                    data = resp.json()
                    if self.provider.is_ready(data):
                        with self._lock:
                            self.failure_count = 0
                        return
                except Exception:
                    pass  # JSON parse failed, treat as unhealthy
        except Exception:
            pass
            
        # Probe failed
        with self._lock:
            self.failure_count += 1
            current_failures = self.failure_count
            
        if current_failures >= FAILURE_THRESHOLD:
            self._attempt_restart()
            
    def _attempt_restart(self):
        # 1. Check cooldown
        now = time.time()
        with self._lock:
            # Prune old timestamps
            self.restart_timestamps = [t for t in self.restart_timestamps if (now - t) < COOLDOWN_SECONDS]
            if len(self.restart_timestamps) >= MAX_RESTARTS:
                logger.warning("[Watchdog] Max restarts reached (cooldown active). Skipping.")
                return
                
            # 2. Check lock file (prevent concurrent restarts)
            if LOCK_FILE.exists():
                try:
                    # If lock file is older than 5 minutes, it's stale
                    if (now - LOCK_FILE.stat().st_mtime) > 300:
                        LOCK_FILE.unlink()
                    else:
                        logger.info("[Watchdog] Restart already in progress. Skipping.")
                        return
                except Exception:
                    pass
                    
            # 3. Acquire lock and restart
            try:
                LOCK_FILE.write_text(str(os.getpid()))
            except Exception:
                return
                
            self.restart_timestamps.append(now)
            self.failure_count = 0 # Reset to prevent immediate re-trigger
            
        logger.warning("[Watchdog] LM Studio unresponsive. Attempting restart...")
        
        try:
            self._execute_restart()
            # Wait for startup
            self._wait_for_recovery()
        finally:
            try:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except Exception:
                pass
                
    def _execute_restart(self):
        cmd = cfg.lm_studio_restart_cmd or self.provider.default_restart_cmd
        if not cmd:
            logger.error(f"[Watchdog] No restart command configured for {self.provider.name}. Cannot restart.")
            return
            
        # Windows-specific detachment
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        try:
            # Split command if it's a string with spaces (e.g., "lms server start")
            args = cmd.split()
            subprocess.Popen(
                args,
                creationflags=creationflags,
                startupinfo=startupinfo,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
            logger.info(f"[Watchdog] Restart command issued: {cmd}")
        except Exception as e:
            logger.error(f"[Watchdog] Failed to execute restart command: {e}")
            
    def _wait_for_recovery(self, timeout: int = 180):
        """Poll until the provider is healthy or timeout."""
        start = time.time()
        while (time.time() - start) < timeout:
            time.sleep(5)
            try:
                resp = httpx.get(self.provider.health_url, timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if self.provider.is_ready(data):
                        logger.info(f"[Watchdog] {self.provider.name} recovered successfully.")
                        return
            except Exception:
                pass
        logger.warning(f"[Watchdog] {self.provider.name} did not recover within timeout.")

# Singleton
watchdog = RuntimeWatchdog()