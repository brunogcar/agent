"""core/router_backend/swarm_fallback.py -- Swarm vote fallback for low-confidence routing.

Extracted from core/router.py v1.0 split. Standalone function:
    - swarm_fallback_route(goal, trace_id)  -- asks swarm to vote on workflow type

[v1.1 #18] Called from route() ONLY when:
  - the Router model was unavailable (so model_route returned None), AND
  - the heuristic fallback produced confidence="low" (the catch-all
    step #18 -- no routing keywords matched), AND
  - cfg.router_swarm_fallback is True (ROUTER_SWARM_FALLBACK=1).

The swarm's vote action asks all configured cloud providers to classify
the goal into one of the valid workflow types. We require unanimous or
majority agreement before overriding the heuristic -- a split/disagreement
swarm verdict is no more confident than the heuristic, so we let the
heuristic stand.

Non-fatal: any exception returns None and the caller falls through to
the heuristic decision. The router_swarm_fallback flag is advisory -- it
must never turn a successful route() call into a failed one.
"""
from __future__ import annotations
from typing import Optional

from core.tracer import tracer
from core.router_backend.decision import RoutingDecision


def swarm_fallback_route(goal: str, trace_id: str) -> Optional[RoutingDecision]:
    """[v1.1 #18] Ask swarm to vote on workflow type when heuristics are uncertain.

    Standalone function (v1.0 split -- was TaskRouter._swarm_fallback_route).
    """
    try:
        from tools.swarm import swarm
        result = swarm(
            action="vote",
            question=(
                "Which workflow type best fits this task? Answer with ONE word: "
                "autocode, research, data, deep_research, understand, or direct.\n\n"
                f"Task: {goal[:500]}"
            ),
            temperature=0,    # deterministic -- vote must measure model agreement, not sampling noise
            max_tokens=20,    # just one word
            timeout=15,
            trace_id=trace_id,
        )
        if result.get("status") != "success":
            return None
        data = result.get("data", {})
        agreement = data.get("agreement", "")
        if agreement not in ("unanimous", "majority"):
            return None  # not confident enough -- let heuristic stand
        # Extract the winning workflow type from the vote groups
        groups = data.get("groups", [])
        if not groups:
            return None
        winner = groups[0]["preview"].strip().lower()
        valid_workflows = {"autocode", "research", "data", "deep_research", "understand", "direct"}
        if winner not in valid_workflows:
            return None
        return RoutingDecision({
            "workflow": winner,
            "tool": "workflow",
            "complexity": 5,
            "reason": f"Swarm vote ({agreement}, {data.get('successful_count', 0)} providers)",
            "confidence": "medium",
        })
    except Exception as e:
        tracer.warning(trace_id, "router", f"Swarm fallback failed (non-fatal): {e}")
        return None
