"""
core/sleep_learn/daemon.py
Phase 1: Main Orchestrator for the Sleep & Learn Daemon.
Checks idle state, runs the sweeper, and logs observations to a JSONL file.
NO LLM calls. NO ChromaDB writes.
"""
from __future__ import annotations
import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any

from core.sleep_learn.config import (
    SLEEP_LEARN_ENABLED,
    SLEEP_LEARN_IDLE_THRESHOLD_SEC,
    OBSERVATION_LOG_FILE
)
from core.sleep_learn.sweeper import sweep_recent_observations

def run_daemon_cycle() -> Dict[str, Any]:
    """
    Executes one cycle of the Sleep & Learn daemon.
    
    Returns:
        Dict containing status, reason, and metrics of the cycle.
    """
    # 1. Kill Switch Check
    if not SLEEP_LEARN_ENABLED:
        return {"status": "disabled", "reason": "SLEEP_LEARN_ENABLED is false in config"}

    # 2. Idle Check (Phase 1: Using a simple time-based mock, replace with actual activity_tracker)
    # TODO: Import actual tracker: from core.runtime.activity_tracker import tracker
    # idle_seconds = tracker.get_idle_time()
    # For Phase 1, we simulate/check a basic condition or just proceed if triggered manually.
    # We will wire the real activity_tracker in the next iteration.
    idle_seconds = 3600  # Placeholder: Assume idle for testing. Replace with tracker.get_idle_time()
    
    if idle_seconds < SLEEP_LEARN_IDLE_THRESHOLD_SEC:
        return {
            "status": "skipped", 
            "reason": f"System not idle for {SLEEP_LEARN_IDLE_THRESHOLD_SEC}s (current idle: {idle_seconds}s)"
        }

    # 3. Sweep for Observations
    observations = sweep_recent_observations(hours=1)
    
    if not observations:
        return {"status": "skipped", "reason": "No high-signal observations found in sweep"}

    # 4. Log to JSONL (Passive Write)
    try:
        os.makedirs(os.path.dirname(OBSERVATION_LOG_FILE) or ".", exist_ok=True)
        with open(OBSERVATION_LOG_FILE, "a", encoding="utf-8") as f:
            for obs in observations:
                obs["_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
                obs["_phase"] = "1_passive_observation"
                f.write(json.dumps(obs, ensure_ascii=False) + "\n")
                
        return {
            "status": "success",
            "observations_logged": len(observations),
            "log_file": OBSERVATION_LOG_FILE
        }
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Failed to write to observation log: {str(e)}"
        }
