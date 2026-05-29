"""
workflows/base.py -- Shared state TypedDict and node utilities.

All three workflows (research, data, autocode) share:
  - WorkflowState TypedDict
  - _step() and _error() node helpers that write to the trace
  - run_workflow() dispatcher that routes by type

Usage from a tool or the agent meta-tool:

    from workflows.base import run_workflow
    result = run_workflow(
        workflow_type = "research",
        goal          = "What is LangGraph?",
        trace_id      = "abc123",
    )
"""
from __future__ import annotations

import time
from typing import Any, Optional
from typing_extensions import TypedDict

from core.tracer import tracer
from core.config  import cfg


# -- Shared workflow state ----------------------------------------------------

class WorkflowState(TypedDict, total=False):
    # Identity
    workflow:    str        # "research" | "data" | "autocode"
    goal:        str        # what we are trying to accomplish
    trace_id:    str        # tracer ID for this run

    # Inputs
    code:        str        # initial code for data workflow
    target_file: str        # file to edit (autocode)
    mode:        str        # autocode mode: fix_error | improve | add_feature
    error_msg:   str        # error traceback (autocode fix_error)
    feature_desc:str        # feature description (autocode add_feature)

    # Accumulated context
    memory_context: str     # recalled memories (formatted string)
    file_content:   str     # current file content (autocode)
    search_results: str     # web search results
    analysis:       str     # agent(analyze) output
    patch:          str     # generated patch (autocode)
    review:         dict    # agent(review) structured output

    # Execution
    output:      str        # python execution output
    exec_error:  str        # execution error if any

    # Control
    retries:     int        # current retry count
    error:       str        # fatal workflow error
    status:      str        # "running" | "success" | "failed"

    # Result
    result:      str        # final result summary
    artifacts:   list       # files created, commits made, etc.


# -- Node helpers -------------------------------------------------------------

def trim_state(state: WorkflowState) -> WorkflowState:
    """
    Phase 5: Evict low-value fields from working memory to the async queue.
    Returns a NEW state dict (Copy-on-Write) to preserve LangGraph immutability.
    """
    from core.memory_backend.budget import estimate_tokens, ContextClass
    from core.memory_backend.eviction import eviction_queue
    from core.config import cfg
    
    # Simple heuristic: If 'search_results' or 'output' is huge, evict it.
    # We keep the state lean to prevent RAM bloat.
    new_state = dict(state)
    evicted_keys = []
    
    for key in ["search_results", "output", "analysis"]:
        val = new_state.get(key)
        if val and isinstance(val, str) and len(val) > 4000: # ~1000 tokens
            # Evict to queue
            eviction_queue.push(
                text=val,
                metadata={"source": key, "trace_id": state.get("trace_id", "")}
            )
            # Replace with placeholder
            new_state[key] = f"[Evicted: {len(val)} chars saved to episodic memory. Use memory tool to recall.]"
            evicted_keys.append(key)
            
    if evicted_keys:
        # Log the eviction
        tid = state.get("trace_id", "")
        if tid:
            tracer.step(tid, "eviction", f"Evicted {evicted_keys} to episodic memory")
            
    return new_state

def node_step(state: WorkflowState, node: str, message: str, checkpoint: bool = False, **kwargs) -> None:
    """Log a workflow step to the active trace."""
    tid = state.get("trace_id", "")
    if tid:
        tracer.step(tid, node, message, **kwargs)
        
    if checkpoint and tid:
        from workflows.helpers.checkpoint import save_checkpoint
        save_checkpoint(tid, node, state)


def node_error(state: WorkflowState, node: str, message: str, **kwargs) -> WorkflowState:
    """Mark state as failed and log to trace. Message is never empty."""
    # Ensure message is never empty -- empty errors are invisible in traces
    if not message or not message.strip():
        message = f"Unspecified error in node '{node}'"

    tid = state.get("trace_id", "")
    if tid:
        tracer.error(tid, node, message, **kwargs)
        from workflows.helpers.checkpoint import save_checkpoint
        save_checkpoint(tid, node, {**state, "status": "failed", "error": message})

    return {**state, "status": "failed", "error": message}


def node_done(state: WorkflowState, result: str, artifacts: list = None) -> WorkflowState:
    """Mark state as succeeded."""
    tid = state.get("trace_id", "")
    if tid:
        tracer.finish(tid, success=True, result=result[:200])
        from workflows.helpers.checkpoint import mark_complete
        mark_complete(tid)

    return {
        **state,
        "status":     "success",
        "result":    result,
        "artifacts": artifacts or [],
    }


# -- Workflow dispatcher ------------------------------------------------------

def run_workflow(
    workflow_type: str,
    goal:          str,
    trace_id:      str  = "",
    resume:        bool = False,
    **kwargs,
) -> dict:
    """
    Run a named workflow and return the final state as a dict.

    workflow_type : "research" | "data" | "autocode"
    goal          : what to accomplish
    trace_id      : attach to existing trace (creates new one if empty)
    resume        : if True, attempt to restore from checkpoint journal
    **kwargs      : workflow-specific inputs (see each workflow module)

    Returns the final WorkflowState as a plain dict with at minimum:
      {status: "success"|"failed", result: str, error: str, artifacts: list}
    """
    wf_type = workflow_type.strip().lower()

    # Create trace if not provided
    if not trace_id:
        trace_id = tracer.new_trace(wf_type, goal=goal)

    initial_state: WorkflowState = {
        "workflow":   wf_type,
        "goal":       goal,
        "trace_id":   trace_id,
        "retries":    0,
        "status":     "running",
        "error":      "",
        "result":     "",
        "artifacts":  [],
        **kwargs,
    }

    # 🔴 CHECKPOINT RESUMPTION
    if resume:
        from workflows.helpers.checkpoint import get_latest
        restored = get_latest(trace_id)
        if restored:
            tracer.step(trace_id, "resume", "Resuming from checkpoint")
            initial_state = {**restored, "status": "running", "goal": goal}
        else:
            tracer.warning(trace_id, "resume", "No checkpoint found, starting fresh")

    # For autocode workflow, convert goal -> task for compatibility with run_autocode_agent
    if wf_type == "autocode":
        initial_state["task"] = goal

    try:
        if wf_type == "research":
            from workflows.research import build_research_graph
            graph  = build_research_graph()
            result = graph.invoke(initial_state)

        elif wf_type == "data":
            from workflows.data import build_data_graph
            graph  = build_data_graph()
            result = graph.invoke(initial_state)

        elif wf_type == "autocode":
            from workflows.autocode import build_autocode_graph
            graph  = build_autocode_graph()
            result = graph.invoke(initial_state)

        else:
            tracer.error( trace_id, "dispatch",
                         f"Unknown workflow type: {wf_type!r}")
            tracer.finish(trace_id, success=False)
            return {
                "status":  "failed",
                "error":  (
                    f"Unknown workflow type '{wf_type}'.  "
                    "Use: research | data | autocode"
                ),
                "result":     "",
                "artifacts": [],
            }

        return dict(result)

    except Exception as e:
        msg = f"Workflow '{wf_type}' crashed: {type(e).__name__}: {e}"
        tracer.error(trace_id, "dispatch", msg)
        tracer.finish(trace_id, success=False, result=msg)
        return {
            "status":     "failed",
            "error":     msg,
            "result":     "",
            "artifacts": [],
        }