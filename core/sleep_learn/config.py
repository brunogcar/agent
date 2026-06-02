"""
core/sleep_learn/config.py
Phase 1: Configuration for the passive observation daemon.
Uses the centralized cfg singleton for all path resolution.
"""
import os
from core.config import cfg

# Toggle the entire daemon on/off
SLEEP_LEARN_ENABLED = os.getenv("SLEEP_LEARN_ENABLED", "true").lower() == "true"

# Idle threshold in seconds before daemon is allowed to run (default: 1 hour)
SLEEP_LEARN_IDLE_THRESHOLD_SEC = int(os.getenv("SLEEP_LEARN_IDLE_THRESHOLD_SEC", "3600"))

# Phase 1 Limits (Preparation for Phase 2 LLM calls)
MAX_CONTEXT_TOKENS_PER_OBSERVATION = 2000

# ── Path Resolution (Centralized via cfg) ──────────────────────────────────
# Logs go to the existing logs/ folder in agent_root
_LOG_DIR = cfg.agent_root / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

OBSERVATION_LOG_FILE = _LOG_DIR / "sleep_learn_observations.jsonl"
