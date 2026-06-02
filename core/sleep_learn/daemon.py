"""
core/sleep_learn/daemon.py
Phase 2: Main Orchestrator for the Sleep & Learn Daemon.
Checks idle state, sweeps observations, and runs active distillation.
"""
from __future__ import annotations
from typing import Dict, Any, List

from core.sleep_learn.config import (
    SLEEP_LEARN_ENABLED,
    SLEEP_LEARN_IDLE_THRESHOLD_SEC,
    SLEEP_LEARN_MAX_DAILY_DISTILLATIONS
)
from core.sleep_learn.sweeper import sweep_recent_observations
from core.sleep_learn.distiller import distill_observation
from core.tracer import tracer
from core.sleep_learn.logger import log_event

def run_daemon_cycle() -> Dict[str, Any]:
    """
    Executes one full cycle of the Sleep & Learn daemon (Phase 2).
    """
    if not SLEEP_LEARN_ENABLED:
        return {"status": "disabled"}

    # Idle Check (Placeholder for actual activity_tracker integration)
    idle_seconds = 3600  # TODO: Replace with tracker.get_idle_time()
    if idle_seconds < SLEEP_LEARN_IDLE_THRESHOLD_SEC:
        return {"status": "skipped", "reason": "System not idle"}

    # 1. Sweep
    observations = sweep_recent_observations(hours=1)
    if not observations:
        return {"status": "skipped", "reason": "No observations to process"}

    # 2. Distill (with strict daily limits to prevent resource exhaustion)
    successes, failures, rejected = 0, 0, 0
    
    for obs in observations[:SLEEP_LEARN_MAX_DAILY_DISTILLATIONS]:
        result = distill_observation(obs)
        status = result.get("status")
        
        if status == "success":
            successes += 1
        elif status == "rejected":
            rejected += 1
        else:
            failures += 1

    summary = {
        "status": "completed",
        "processed": len(observations),
        "rules_learned": successes,
        "rules_rejected": rejected,
        "distillation_errors": failures
    }
    
    tracer.info("daemon", "sleep_learn", "cycle_completed", **summary)
    log_event({"event": "cycle_completed", **summary})
    return summary
