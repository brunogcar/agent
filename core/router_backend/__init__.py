"""core/router_backend/ -- Implementation package for the task router.

All public symbols are re-exported by the thin facade at core/router.py.
Callers should normally import from core.router, not from this package.

Modules:
    decision.py       -- RoutingDecision dataclass
    constants.py      -- ROUTER_SYSTEM_PROMPT, ROUTER_FEW_SHOT_EXAMPLES, etc.
    heuristics.py     -- Pre-compiled regex patterns + heuristic_route()
    model_route.py    -- model_route() + _extract_first_json()
    swarm_fallback.py -- swarm_fallback_route()
    complexity.py     -- classify_complexity()
    telemetry.py      -- [v1.0] Routing telemetry (heuristic vs model disagreements)
    adaptive.py       -- [v1.0] Adaptive complexity thresholds
    router_engine.py  -- TaskRouter class (the public entry point)
"""
