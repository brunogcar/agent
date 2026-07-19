"""Human-in-the-Loop approval gate.

[v3.4 #38] Pauses the workflow before commit when AUTOCODE_HITL_ENABLED=1.
Uses the async-checkpoint-resume pattern:
  1. Saves checkpoint via save_checkpoint(tid, "hitl", state)
  2. Returns {"status": "awaiting_approval"}
  3. The graph routes to END (workflow pauses)
  4. User reviews the changes
  5. User resumes: run_workflow("autocode", goal="...", resume=True, hitl_approved=True)
  6. On resume, the gate sees hitl_approved=True and passes through to node_commit

When AUTOCODE_HITL_ENABLED=0 (default), the gate is a no-op (returns {}).
"""
from __future__ import annotations

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState


def node_hitl_gate(state: AutocodeState) -> dict:
    """Human-in-the-Loop approval gate before commit.

    When AUTOCODE_HITL_ENABLED=1 (default OFF):
    - If hitl_approved is False: save checkpoint + return {"status": "awaiting_approval"}
    - If hitl_approved is True: return {} (pass through to commit)

    When disabled: return {} (no-op).
    """
    # [v3.4 #38] If HiTL is disabled, pass through
    if not getattr(cfg, "autocode_hitl_enabled", False):
        return {}

    # If already approved, pass through
    if state.get("hitl_approved", False):
        return {}

    # Awaiting approval — save checkpoint + pause
    tid = state.get("trace_id", "")
    tracer.step(tid, "hitl_gate", "Workflow paused — awaiting human approval before commit")

    try:
        from core.observability.checkpoint import save_checkpoint
        save_checkpoint(tid, "hitl", state)
    except Exception:
        pass  # Non-fatal — checkpoint failure shouldn't block the pause

    return {"status": "awaiting_approval"}
