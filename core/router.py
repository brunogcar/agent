"""core/router.py -- Thin facade for the task router.

All implementation logic lives in core/router_backend/ (v1.0 split).
This module re-exports the public surface area so existing callers
(workflow tool, dispatcher, gateway) and tests are unaffected.

Usage:
    from core.router import router
    decision = router.route("Fix the timeout bug in tools/web.py")

Public symbols re-exported:
    router                       -- TaskRouter singleton
    TaskRouter                   -- class (for type hints and direct instantiation)
    RoutingDecision              -- structured routing result
    ROUTER_SYSTEM_PROMPT         -- canonical router system prompt
    ROUTER_FEW_SHOT_EXAMPLES    -- few-shot examples for the prompt
    ROUTER_TOOLS                 -- canonical list of tool names
    ROUTER_WORKFLOWS             -- canonical list of workflow names

[v1.0 NEW] Telemetry and adaptive thresholds are accessible via:
    from core.router_backend.telemetry import get_telemetry, get_telemetry_summary
    from core.router_backend.adaptive import apply_adaptive_thresholds, COMPLEXITY_THRESHOLD
"""
from __future__ import annotations

from core.router_backend.router_engine import TaskRouter
from core.router_backend.decision import RoutingDecision
from core.router_backend.constants import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_FEW_SHOT_EXAMPLES,
    ROUTER_TOOLS,
    ROUTER_WORKFLOWS,
)

# -- Singleton ----------------------------------------------------------------
router = TaskRouter()
