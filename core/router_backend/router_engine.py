"""core/router_backend/router.py -- TaskRouter class (public entry point).

Extracted from core/router.py v1.0 split. The TaskRouter class is now a
thin orchestrator: it delegates to standalone functions in the sibling
backend modules and adds two v1.0 features on top:

  - apply_adaptive_thresholds() -- downgrade confidence for complex+low tasks
  - log_routing_telemetry()     -- log heuristic-vs-model disagreements

The class retains the public surface area (route, classify_complexity) so
existing callers (workflow tool, dispatcher, gateway) are unaffected.
"""
from __future__ import annotations
from typing import Optional

from core.config import cfg
from core.tracer import tracer

from core.router_backend.decision import RoutingDecision
from core.router_backend.model_route import model_route
from core.router_backend.heuristics import heuristic_route
from core.router_backend.swarm_fallback import swarm_fallback_route
from core.router_backend.complexity import classify_complexity as _classify_complexity
from core.router_backend.adaptive import apply_adaptive_thresholds
from core.router_backend.telemetry import log_routing_telemetry


class TaskRouter:
    """Routes tasks to the appropriate workflow.

    Three-tier routing:
      1. Model-based routing via the Router role (model_route).
      2. Heuristic fallback (heuristic_route) -- regex pattern matching.
      3. [v1.1 #18] Swarm vote fallback for low-confidence heuristic decisions
         (only when cfg.router_swarm_fallback is True).

    v1.0 additions:
      - Adaptive complexity thresholds (apply_adaptive_thresholds) -- complex
        tasks (>7) without high confidence get downgraded + a clarifying
        question.
      - Routing telemetry (log_routing_telemetry) -- heuristic_route is
        always invoked (cheap regex) so we can compare what it WOULD have
        returned against what the model actually returned. Disagreements
        are flagged in the in-memory telemetry log for later analysis.
    """

    def route(
        self,
        goal: str,
        trace_id: str = "",
    ) -> RoutingDecision:
        """Route a goal to the best workflow.

        Tries the Router model first, falls back to heuristics on failure,
        and optionally consults the swarm for low-confidence heuristic
        decisions. Always runs the heuristic in parallel for telemetry
        (cheap -- just regex).
        """
        # Empty goal short-circuit -- skip heuristic_route and telemetry.
        if not goal.strip():
            return RoutingDecision({
                "workflow": "research", "tool": "web",
                "complexity": 1, "reason": "Empty goal",
                "confidence": "low",
                "clarifying_questions": ["What would you like me to help you with?"]
            })

        if trace_id:
            tracer.step(trace_id, "router", "routing task", goal=goal[:60])

        # [v1.0 telemetry] Always run the heuristic so we can log disagreements.
        # Cheap (single-pass regex); does NOT call the LLM.
        heuristic_decision = heuristic_route(goal)
        heuristic_workflow = heuristic_decision.workflow

        # 1. Try model-based routing
        model_decision = model_route(goal, trace_id)
        if model_decision:
            model_decision = apply_adaptive_thresholds(model_decision)
            log_routing_telemetry(
                goal,
                model_decision.workflow,   # what the model said
                heuristic_workflow,         # what heuristic would have said
                model_decision.workflow,    # what we're actually returning
                model_decision.confidence,
                trace_id,
            )
            if trace_id:
                tracer.step(trace_id, "router",
                    f"routed to {model_decision.workflow} (model)",
                    complexity=model_decision.complexity)
            return model_decision

        # 2. Fall back to heuristics (already computed above for telemetry)
        decision = heuristic_decision

        # 3. [v1.1 #18] Swarm fallback for low-confidence routing
        if decision.confidence == "low" and getattr(cfg, "router_swarm_fallback", False):
            swarm_decision = swarm_fallback_route(goal, trace_id)
            if swarm_decision:
                swarm_decision = apply_adaptive_thresholds(swarm_decision)
                log_routing_telemetry(
                    goal,
                    None,                       # model failed
                    heuristic_workflow,
                    swarm_decision.workflow,
                    swarm_decision.confidence,
                    trace_id,
                )
                if trace_id:
                    tracer.step(trace_id, "router",
                        f"routed to {swarm_decision.workflow} (swarm)",
                        complexity=swarm_decision.complexity)
                return swarm_decision

        # 4. Apply adaptive thresholds + log telemetry
        decision = apply_adaptive_thresholds(decision)
        log_routing_telemetry(
            goal,
            None,
            heuristic_workflow,
            decision.workflow,
            decision.confidence,
            trace_id,
        )
        if trace_id:
            tracer.step(trace_id, "router",
                f"routed to {decision.workflow} (heuristic)",
                complexity=decision.complexity)
        return decision

    def classify_complexity(self, goal: str) -> int:
        """Quick complexity score (1-10) for a goal. Delegates to the
        standalone classify_complexity() in complexity.py.
        """
        return _classify_complexity(goal)
