"""
core/sleep_learn/daemon.py
Background daemon for Sleep & Learn feedback processing.
Designed for non-24/7 usage: runs at startup, and catches midnight if the agent stays running.
"""
import threading
import time
import logging
from core.sleep_learn.feedback import process_feedback

def _daemon_loop():
    """Runs feedback at startup, then checks hourly for midnight."""
    # 1. Run immediately at startup
    logging.info("[Sleep & Learn] Running initial feedback processing at startup...")
    try:
        process_feedback()
    except Exception as e:
        logging.error(f"[Sleep & Learn] Startup feedback failed: {e}")

    last_run_date = time.strftime('%Y-%m-%d')
    
    # 2. Loop to catch midnight if the agent stays running
    while True:
        time.sleep(3600)  # Check every hour to avoid busy-waiting
        current_date = time.strftime('%Y-%m-%d')
        current_hour = time.localtime().tm_hour
        
        # If it's midnight (hour 0) and we haven't run today yet
        if current_hour == 0 and current_date != last_run_date:
            logging.info("[Sleep & Learn] Running scheduled midnight feedback processing...")
            try:
                process_feedback()
                last_run_date = current_date
            except Exception as e:
                logging.error(f"[Sleep & Learn] Midnight feedback failed: {e}")

def start_background_daemon():
    """Starts the Sleep & Learn daemon in a background thread."""
    thread = threading.Thread(target=_daemon_loop, daemon=True, name="SleepLearnDaemon")
    thread.start()