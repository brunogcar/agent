
# ── Sleep & Learn Background Daemon ──
# Starts automatically on agent boot to process pending feedback.
# Runs at startup, and catches midnight if the agent remains running.
try:
    from core.sleep_learn.daemon import start_background_daemon
    start_background_daemon()
except Exception as e:
    import logging
    logging.warning(f"Failed to start Sleep & Learn daemon: {e}")