"""
core/sleep_learn/daemon.py
Background daemon for Sleep & Learn feedback processing.
Designed for non-24/7 usage: runs at startup, and catches midnight if the agent stays running.
v1.0: Added idle detection — the daemon now gates on tracker.try_acquire_background_slot()
before running, preventing unnecessary resource usage in test/short-lived sessions.
"""
import threading
import time
import logging
from core.sleep_learn.feedback import process_feedback

# v1.0: Idle detection threshold. The daemon waits this many seconds of agent
# inactivity before running. Prevents the daemon from starting in test
# environments or short-lived scripts. Set to 0 to disable (always run).
SLEEP_LEARN_IDLE_THRESHOLD_SEC = 300  # 5 minutes — conservative for local-first use

def _daemon_loop():
    """Runs feedback at startup (if idle), then checks hourly for midnight.
    
    v1.0: Added idle detection gate. The daemon does NOT run immediately at
    startup — it waits for the agent to be idle for SLEEP_LEARN_IDLE_THRESHOLD_SEC
    seconds first. This prevents the daemon from starting in test environments
    or short-lived scripts (the #1 complaint in the collective review).
    """
    from core.runtime.activity_tracker import tracker
    
    # 1. Wait for idle before running initial feedback
    logging.info(f"[Sleep & Learn] Waiting for {SLEEP_LEARN_IDLE_THRESHOLD_SEC}s idle before initial feedback...")
    idle_waited = False
    _idle_event = threading.Event()
    for _ in range(SLEEP_LEARN_IDLE_THRESHOLD_SEC // 10):
        if tracker.try_acquire_background_slot(min_idle_seconds=SLEEP_LEARN_IDLE_THRESHOLD_SEC):
            idle_waited = True
            break
        _idle_event.wait(timeout=10)  # Event.wait, not time.sleep — immune to time.sleep mocks
    
    if not idle_waited:
        # Force-run after the threshold anyway (timeout — don't block forever)
        tracker.try_acquire_background_slot(min_idle_seconds=0)
    
    logging.info("[Sleep & Learn] Running initial feedback processing...")
    try:
        process_feedback()
    except Exception as e:
        logging.error(f"[Sleep & Learn] Startup feedback failed: {e}")
    finally:
        tracker.release_background_slot()

    last_run_date = time.strftime('%Y-%m-%d')
    
    # 2. Loop to catch midnight if the agent stays running
    while True:
        _hourly_event = threading.Event()
        _hourly_event.wait(timeout=3600)  # Event.wait, not time.sleep — immune to time.sleep mocks
        current_date = time.strftime('%Y-%m-%d')
        current_hour = time.localtime().tm_hour
        
        # If it's midnight (hour 0) and we haven't run today yet
        if current_hour == 0 and current_date != last_run_date:
            # v1.0: Also gate midnight run on idle
            if tracker.try_acquire_background_slot(min_idle_seconds=SLEEP_LEARN_IDLE_THRESHOLD_SEC):
                logging.info("[Sleep & Learn] Running scheduled midnight feedback processing...")
                try:
                    process_feedback()
                    last_run_date = current_date
                except Exception as e:
                    logging.error(f"[Sleep & Learn] Midnight feedback failed: {e}")
                finally:
                    tracker.release_background_slot()

def start_background_daemon():
    """Starts the Sleep & Learn daemon in a background thread."""
    thread = threading.Thread(target=_daemon_loop, daemon=True, name="SleepLearnDaemon")
    thread.start()