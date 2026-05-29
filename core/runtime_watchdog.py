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

logger = logging.getLogger(__name__)

PROBE_URL = f"{cfg.lm_studio_base_url}/models"
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
            resp = httpx.get(PROBE_URL, timeout=3.0)
            if resp.status_code == 200:
                # Healthy: reset failure count
                with self._lock:
                    self.failure_count = 0
                return
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
        cmd = cfg.lm_studio_restart_cmd
        if not cmd:
            logger.error("[Watchdog] LM_STUDIO_RESTART_CMD is empty. Cannot restart.")
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
            
    def _wait_for_recovery(self, timeout: int = 90):
        """Poll until LM Studio is healthy or timeout."""
        start = time.time()
        while (time.time() - start) < timeout:
            time.sleep(5)
            try:
                resp = httpx.get(PROBE_URL, timeout=3.0)
                if resp.status_code == 200:
                    logger.info("[Watchdog] LM Studio recovered successfully.")
                    return
            except Exception:
                pass
        logger.warning("[Watchdog] LM Studio did not recover within timeout.")

# Singleton
watchdog = RuntimeWatchdog()