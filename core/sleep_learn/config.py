"""
core/sleep_learn/config.py
Phase 2: Configuration for the Active Distillation daemon.
Uses the centralized cfg singleton for all path resolution.
"""
import os
from core.config import cfg

# Toggle the entire daemon on/off
SLEEP_LEARN_ENABLED = os.getenv("SLEEP_LEARN_ENABLED", "true").lower() == "true"

# Idle threshold in seconds before daemon is allowed to run (default: 1 hour)
SLEEP_LEARN_IDLE_THRESHOLD_SEC = int(os.getenv("SLEEP_LEARN_IDLE_THRESHOLD_SEC", "3600"))

# Phase 2: Distillation Limits
SLEEP_LEARN_COLLECTION_NAME = "procedural_meta"
SLEEP_LEARN_MIN_RULE_WORDS = int(os.getenv("SLEEP_LEARN_MIN_RULE_WORDS", "10"))
SLEEP_LEARN_MAX_DAILY_DISTILLATIONS = int(os.getenv("SLEEP_LEARN_MAX_DAILY_DISTILLATIONS", "20"))

# Path Resolution (Centralized via cfg)
_LOG_DIR = cfg.agent_root / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
OBSERVATION_LOG_FILE = _LOG_DIR / "sleep_learn_observations.jsonl"

# Physical isolation: Separate ChromaDB instance for learned rules
_SLEEP_LEARN_DB_PATH = cfg.memory_root / "sleep_learn_db"
_SLEEP_LEARN_DB_PATH.mkdir(parents=True, exist_ok=True)
