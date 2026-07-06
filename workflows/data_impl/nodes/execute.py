"""Node: execute — Generate (if needed) and execute Python data-analysis code.

Two paths:
  - If `code` is already in state (user-provided), run it directly.
  - If no code, ask agent(role="code") to generate it, then run it.

[Fix #1]  Returns partial update dicts (was {**state, ...}).
[Fix #2]  Code-gen failure now sets `exec_error` so route_after_execute sends
          it to END (previously it returned node_error() which set status:failed
          but NOT exec_error, so the router wrongly sent it to critique).
[Fix #3]  Execution failure now calls node_error() (trace + checkpoint);
          previously it only called node_step() — no error trace, no checkpoint.
[Fix #5]  Sets `code_generated` so node_store knows whether the code was
          LLM-generated (only generated code is stored as procedural memory).
[Fix #8]  agent() and python() calls are wrapped in try/except so an unexpected
          exception is converted to exec_error instead of crashing the workflow.
[Fix #9]  Code extraction uses the _extract_code_from_response helper, which
          logs fallbacks via tracer.warning (was a silent `import re` inline).
"""
from __future__ import annotations

from workflows.base import WorkflowState, node_step, node_error
from workflows.data_impl.helpers import _extract_code_from_response


def node_execute(state: WorkflowState) -> dict:
    """Execute the provided Python code, generating it first if absent."""
    from tools.python import python

    code = state.get("code", "")
    goal = state.get("goal", "")
    tid = state.get("trace_id", "")
    code_generated = False

    if not code:
        # No code provided — ask executor to generate it.
        from tools.agent import agent
        node_step(state, "execute", "no code provided — generating")

        try:
            r = agent(
                action="dispatch",
                role="code",
                task=f"Write Python code to: {goal}. Use print() for all output.",
                context=state.get("memory_context", ""),
                trace_id=tid,
            )
        except Exception as e:
            # [Fix #8] agent() unexpectedly raised — treat as code-gen failure.
            return {**node_error(state, "execute", f"Code generation raised: {e}"),
                    "exec_error": f"Code generation raised: {e}", "output": ""}

        if r.get("status") != "success":
            # [Fix #2] Set exec_error so route_after_execute -> END.
            msg = f"Code generation failed: {r.get('error', 'unknown')}"
            return {**node_error(state, "execute", msg),
                    "exec_error": msg, "output": ""}

        # [Fix #9] Extract via helper with observable fallbacks.
        code = _extract_code_from_response(r.get("parsed"), r.get("text", ""), tid)
        code_generated = True

    node_step(state, "execute", "running code", chars=len(code))

    try:
        result = python(mode="run_data", code=code)
    except Exception as e:
        # [Fix #8] python() unexpectedly raised — treat as execution failure.
        return {**node_error(state, "execute", f"Execution raised: {e}"),
                "exec_error": f"Execution raised: {e}", "output": "",
                "code": code, "code_generated": code_generated}

    if result.get("status") != "success":
        error = result.get("error", "unknown error")
        # [Fix #3] Call node_error so the failure is traced + checkpointed
        # (was only node_step — no error trace, no checkpoint).
        return {**node_error(state, "execute", f"Execution failed: {error[:200]}"),
                "exec_error": error, "output": "",
                "code": code, "code_generated": code_generated}

    output = result.get("output", "(no output)")
    node_step(state, "execute", "execution successful", output_chars=len(output))
    return {
        "output": output,
        "exec_error": "",
        "code": code,
        # [Fix #5] Flag so node_store only stores procedural memory for
        # LLM-generated code, not user-provided code.
        "code_generated": code_generated,
    }
