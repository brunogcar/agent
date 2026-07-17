"""
core/sleep_learn/sweeper.py
v1.0: Passive Observation Sweeper — integrated with tracer + memory.
Gathers high-signal events (errors, retries, corrections) for distillation.
NO LLM calls. NO ChromaDB writes. Pure observation gathering.

v1.0 changes (was Phase 1 placeholder):
- Reads recent traces via tracer.recent() — finds errors, retries, failures
- Reads recent episodic memories via memory.recall() — finds task outcomes
- Returns structured observations ready for the distiller
- Filters by signal strength (high = errors/failures, medium = retries, low = successes)
"""
from __future__ import annotations
import time
from typing import List, Dict, Any

from core.tracer import tracer


def sweep_recent_observations(hours: int = 1) -> List[Dict[str, Any]]:
    """
    Queries recent high-signal events for distillation candidates.
    
    v1.0: Reads from two sources:
    1. tracer.recent() — finds errors, retries, failures in execution traces
    2. memory.recall() — finds episodic memories with outcome="failure"
    
    Returns a list of observation dicts, each with:
    - event_type: "error" | "retry" | "failure" | "success" | "correction"
    - signal_strength: "high" | "medium" | "low"
    - message: the observation text (what happened)
    - memory_id: the origin trace/memory ID (for source tracking)
    - trace_id: the trace ID (for provenance)
    - hours_scanned: how many hours of history were scanned
    """
    observations = []
    cutoff = time.time() - (hours * 3600)
    
    # ── Source 1: Recent traces from the tracer ──────────────────────────
    try:
        recent_traces = tracer.recent(n=50)
        for trace in recent_traces:
            trace_ts = trace.get("started_at", 0)
            if trace_ts < cutoff:
                continue
            
            events = trace.get("events", [])
            for event in events:
                event_msg = event.get("msg", "")
                event_name = event.get("event", "")
                
                # High signal: errors
                if event_name == "error" or "error" in event_msg.lower():
                    observations.append({
                        "event_type": "error",
                        "signal_strength": "high",
                        "message": event_msg[:500],
                        "memory_id": trace.get("trace_id", ""),
                        "trace_id": trace.get("trace_id", ""),
                        "hours_scanned": hours,
                    })
                
                # Medium signal: retries (workflow nodes that re-ran)
                elif "retry" in event_name.lower() or "retry" in event_msg.lower():
                    observations.append({
                        "event_type": "retry",
                        "signal_strength": "medium",
                        "message": event_msg[:500],
                        "memory_id": trace.get("trace_id", ""),
                        "trace_id": trace.get("trace_id", ""),
                        "hours_scanned": hours,
                    })
                
                # Medium signal: corrections (debug cycles)
                elif "debug" in event_name.lower() or "correction" in event_msg.lower():
                    observations.append({
                        "event_type": "correction",
                        "signal_strength": "medium",
                        "message": event_msg[:500],
                        "memory_id": trace.get("trace_id", ""),
                        "trace_id": trace.get("trace_id", ""),
                        "hours_scanned": hours,
                    })
    except Exception:
        pass  # Tracer may not be available in all environments
    
    # ── Source 2: Recent episodic memories with failures ─────────────────
    try:
        from core.memory_engine import memory
        failure_results = memory.recall(
            query="error failure task did not complete",
            collections=["episodic"],
            top_k=20,
            min_score=0.3,  # loose — we want broad coverage
        )
        
        for result in failure_results:
            meta = result.get("metadata", {})
            outcome = meta.get("outcome", "")
            
            if outcome == "failure":
                observations.append({
                    "event_type": "failure",
                    "signal_strength": "high",
                    "message": result.get("text", "")[:500],
                    "memory_id": result.get("id", ""),
                    "trace_id": meta.get("trace_id", ""),
                    "hours_scanned": hours,
                })
            elif outcome == "success":
                # Low signal: successes (rules can be distilled from what worked)
                observations.append({
                    "event_type": "success",
                    "signal_strength": "low",
                    "message": result.get("text", "")[:500],
                    "memory_id": result.get("id", ""),
                    "trace_id": meta.get("trace_id", ""),
                    "hours_scanned": hours,
                })
    except Exception:
        pass  # Memory may not be available in all environments
    
    # Cap to prevent overwhelming the distiller
    max_observations = 50
    if len(observations) > max_observations:
        # Sort by signal strength (high > medium > low) and take top N
        priority = {"high": 0, "medium": 1, "low": 2}
        observations.sort(key=lambda o: priority.get(o.get("signal_strength", "low"), 3))
        observations = observations[:max_observations]
    
    return observations
