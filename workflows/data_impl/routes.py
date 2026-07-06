"""Routing functions for the data workflow.

[Fix #10] route_after_critique was removed — it always returned "store",
making the conditional edge dead code. critique -> store is now a direct edge.
Only route_after_execute remains; it is a genuine conditional router.
"""
from __future__ import annotations

from workflows.base import WorkflowState


def route_after_execute(state: WorkflowState) -> str:
    """After execute: route to critique on success, END on failure.

    [Fix #2/#3] Both failure paths (code-gen failure and execution failure)
    now set `exec_error`, so this router correctly sends failures to END
    instead of letting them fall through to critique. Previously code-gen
    failure returned node_error() (which sets status:failed but NOT
    exec_error), so the router returned "critique" and the workflow tried
    to critique an empty output.
    """
    if state.get("exec_error"):
        return "failed"
    return "critique"
