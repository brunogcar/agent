
# ── Sleep & Learn Background Daemon ──
# Starts automatically on agent boot to process pending feedback.
# Runs at startup, and catches midnight if the agent remains running.
_daemon_started = False

def _start_daemon_once():
    global _daemon_started
    if not _daemon_started:
        try:
            from core.sleep_learn.daemon import start_background_daemon
            start_background_daemon()
            _daemon_started = True
        except Exception as e:
            import logging
            logging.warning(f"Failed to start Sleep & Learn daemon: {e}")

_start_daemon_once()