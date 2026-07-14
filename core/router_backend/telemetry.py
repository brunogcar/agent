"""core/router_backend/telemetry.py -- Routing telemetry.

[v1.0 NEW] Log heuristic vs model route disagreements.

Lightweight in-memory tracking (like agent metrics). When the model route
disagrees with the heuristic route (different workflow type), log it so we
can identify real-world routing failures.

This is the P2 roadmap item: "Log heuristic vs LLM route disagreements".

Design:
    - log_routing_telemetry() is called from TaskRouter.route() after the
      final decision is made.
    - heuristic_route() is always invoked (cheap -- just regex, microseconds)
      so we can compare what the heuristic WOULD have returned against what
      the model actually returned.
    - If model_workflow is not None and differs from heuristic_workflow,
      the entry is flagged as a disagreement -- these are the interesting
      cases for identifying routing failures.
    - The log is bounded (_MAX_LOG_ENTRIES) and FIFO -- oldest entries drop.
"""
from __future__ import annotations
from typing import Any

_telemetry_log: list[dict] = []
_MAX_LOG_ENTRIES = 100


def log_routing_telemetry(
    goal: str,
    model_workflow: str | None,
    heuristic_workflow: str,
    final_workflow: str,
    confidence: str,
    trace_id: str = "",
) -> None:
    """Log a routing decision for telemetry.

    Called from route() after the final decision is made. If model_workflow
    is not None and differs from heuristic_workflow, it's a disagreement --
    these are the interesting cases for identifying routing failures.
    """
    entry = {
        "goal_preview": goal[:100],
        "model_workflow": model_workflow,
        "heuristic_workflow": heuristic_workflow,
        "final_workflow": final_workflow,
        "confidence": confidence,
        "disagreement": model_workflow is not None and model_workflow != heuristic_workflow,
    }
    _telemetry_log.append(entry)
    if len(_telemetry_log) > _MAX_LOG_ENTRIES:
        _telemetry_log.pop(0)  # drop oldest


def get_telemetry() -> list[dict]:
    """Return a copy of the telemetry log."""
    return list(_telemetry_log)


def get_telemetry_summary() -> dict:
    """Return summary stats: total, disagreements, disagreement_rate."""
    total = len(_telemetry_log)
    disagreements = sum(1 for e in _telemetry_log if e["disagreement"])
    return {
        "total": total,
        "disagreements": disagreements,
        "disagreement_rate": disagreements / total if total > 0 else 0.0,
    }


def clear_telemetry() -> None:
    """Clear the telemetry log."""
    _telemetry_log.clear()
