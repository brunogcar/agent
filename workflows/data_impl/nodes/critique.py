"""Node: critique — Have the executor critique the execution output quality.

[Fix #1]  Returns partial update dicts (was {**state, ...}).
[Fix #4]  Uses `context=` (text) instead of `content=` (base64 image) to pass
          the code output to agent(role="critique"). content is for vision;
          context is for text. Confirmed in tools/agent_ops/actions/dispatch.py:
          both flow to llm.complete(), but context is the primary text channel.
[Fix #6]  Empty-output skip is now logged via tracer (was a silent `return state`).
[Fix #7]  Critique failure is now logged via tracer.error (was a silent fallback
          that used raw output as the result with no trace of the failure).
[Fix #8]  agent() call is wrapped in try/except so an unexpected exception is
          logged and the workflow still produces a result from the raw output.
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step
from core.tracer import tracer


def node_critique(state: WorkflowState) -> dict:
    """Evaluate whether the execution output adequately answers the goal."""
    from tools.agent import agent

    output = state.get("output", "")
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")

    if not output:
        # [Fix #6] Log why critique is skipped (was silent `return state`).
        node_step(state, "critique", "skipped — no execution output to critique")
        return {}

    node_step(state, "critique", "evaluating output quality")

    try:
        r = agent(
            action="dispatch",
            role="critique",
            task=(
                f"Does this output adequately answer: '{goal}'? "
                "Note any missing analysis, errors, or improvements."
            ),
            # [Fix #4] context= for text (content= is for base64 images).
            context=f"Code output:\n{output[:1000]}",
            trace_id=tid,
        )
    except Exception as e:
        # [Fix #8] agent() unexpectedly raised — log and use raw output.
        tracer.error(tid, "critique", f"agent() raised: {e}")
        return {"result": output}

    if r.get("status") == "success":
        node_step(state, "critique", "critique complete")
        return {"result": f"OUTPUT:\n{output}\n\nANALYSIS:\n{r['text']}"}

    # [Fix #7] Log the critique failure (was a silent fallback).
    tracer.error(tid, "critique", f"critique failed: {r.get('error', 'unknown')}")
    return {"result": output}
