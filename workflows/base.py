"""workflows/base.py -- Shared state TypedDict, node helpers, and dispatcher.

All six workflows (research, data, autocode, deep_research, understand) share:
  WorkflowState TypedDict
  node_step() and node_error() and node_done() helpers that write to the trace
  run_workflow() dispatcher that routes by type

Usage from a tool or the agent meta-tool:
    from workflows.base import run_workflow
    result = run_workflow(
        workflow_type="research",
        goal="What is LangGraph?",
        trace_id="abc123",
    )
"""
from __future__ import annotations
import time
from typing import Any, Optional
from typing_extensions import TypedDict
from core.tracer import tracer
from core.config import cfg

# -- Shared workflow state ----------------------------------------------------
class WorkflowState(TypedDict, total=False):
    # Identity
    workflow: str          # "research" | "data" | "autocode" | "deep_research" | "understand"
    goal: str              # what we are trying to accomplish
    trace_id: str          # tracer ID for this run
    # Inputs
    code: str              # initial code for data workflow
    target_file: str       # file to edit (autocode)
    mode: str              # autocode mode: fix_error | improve | add_feature
    error_msg: str         # error traceback (autocode fix_error)
    feature_desc: str      # feature description (autocode add_feature)
    task: str              # [v1.2] autocode task (same as goal; autocode uses task internally)

    # Accumulated context
    memory_context: str      # recalled memories (formatted string)
    file_content: str        # current file content (autocode)
    search_results: str      # web search results
    analysis: str            # agent(analyze) output
    patch: str               # generated patch (autocode)
    review: dict             # agent(review) structured output

    # Execution
    output: str              # python execution output
    exec_error: str          # execution error if any

    # Control
    retries: int             # current retry count
    error: str               # fatal workflow error
    status: str              # "running" | "success" | "failed"

    # Result
    result: str              # final result summary
    artifacts: list          # files created, commits made, etc.

# -- Node helpers -------------------------------------------------------------
# NOTE: node_step, node_error, and node_done are HELPERS called inside node
# functions, NOT LangGraph nodes themselves. They handle trace logging and
# checkpointing. node_step returns None (side-effect only); node_error and
# node_done return partial dicts for LangGraph to merge.

def trim_state(state: WorkflowState) -> WorkflowState:
    """
    Phase 5: Evict low-value fields from working memory to the async queue.
    Returns a NEW state dict (Copy-on-Write) to preserve LangGraph immutability.

    v1.3: Chonkie-aware eviction. When chonkie is available, splits oversized
    fields into sentence-aware chunks and evicts each chunk individually (enabling
    precise recall later). Keeps the first chunk as a preview in state so the LLM
    has context without needing to recall immediately. Falls back to whole-string
    eviction (v1.0 behavior) if chonkie is not installed or chunking fails.

    NOTE: trim_state() is currently a utility — no workflow calls it yet. It's
    ready for when workflows wire it into their graphs (see base/CHANGELOG.md #18).
    When wired in, it should be called between nodes that produce large outputs
    (e.g., after search_results is populated, before the next node runs).
    """
    from core.memory_backend.eviction import eviction_queue
    new_state = dict(state)
    evicted_keys = []
    trace_id = state.get("trace_id", "")

    for key in ["search_results", "output", "analysis"]:
        val = new_state.get(key)
        if val and isinstance(val, str) and (len(val) // 4) > 1000:
            _evict_field(new_state, key, val, trace_id)
            evicted_keys.append(key)

    if evicted_keys:
        tid = state.get("trace_id", "")
        if tid:
            tracer.step(tid, "eviction", f"Evicted {evicted_keys} to episodic memory")

    return new_state


def _evict_field(new_state: dict, key: str, val: str, trace_id: str) -> None:
    """Evict an oversized field. Tries chonkie-aware chunked eviction first,
    falls back to whole-string eviction (v1.0 behavior) if chonkie is missing
    or chunking fails.

    Chonkie path (v1.3):
      1. Split text into sentence-aware chunks via _chunk_text() (reuses file
         tool v1.2 integration — same chonkie SentenceChunker, lazy import)
      2. Evict each chunk individually to episodic memory. The `source` field
         encodes the field name and chunk position (e.g., "evicted:output:chunk_2_of_5")
         so the LLM can recall specific chunks later via tags_filter="evicted"
      3. Keep first chunk (~500 chars) as preview in state — gives the LLM
         enough context to decide whether to recall, instead of a blind placeholder

    Fallback path (v1.0 behavior):
      1. Evict whole string to episodic memory
      2. Replace with generic placeholder (no preview)

    Why `source` encodes chunk position (not source_doc_id metadata):
      The eviction flusher (core/memory_backend/eviction.py flusher_loop) unpacks
      metadata as kwargs to memory.store(). memory.store() accepts specific params
      (text, memory_type, importance, tags, trace_id, goal, outcome, tools_used,
      source) — NOT source_doc_id/chunk_index/chunk_count. Adding those would
      cause TypeError. The `source` field (truncated to 200 chars by execute_store)
      is the right place to encode chunk position for evicted memories.
    """
    token_count = len(val) // 4

    # Import eviction_queue (needed for both chonkie and fallback paths).
    # Imported inside the function to match trim_state()'s pattern and avoid
    # module-level import side effects.
    from core.memory_backend.eviction import eviction_queue

    # Try chonkie-aware eviction
    try:
        from tools.file_ops.actions.read_file import _chunk_text
        chunks = _chunk_text(val, "sentence", 512)
        if chunks and len(chunks) > 1:
            # Evict each chunk individually — source field encodes position for recall
            for idx, chunk in enumerate(chunks):
                eviction_queue.push(
                    text=chunk,
                    metadata={
                        "source": f"evicted:{key}:chunk_{idx}_of_{len(chunks)}",
                        "trace_id": trace_id,
                    }
                )
            # Keep first chunk as preview (~500 chars) so LLM has context
            preview = chunks[0][:500]
            if len(chunks[0]) > 500:
                preview += "..."
            new_state[key] = (
                f"[Evicted: {token_count} tokens across {len(chunks)} chunks saved to episodic memory. "
                f'Preview: "{preview}". '
                f'Use memory(recall, tags_filter="evicted") to retrieve specific chunks.]'
            )
            return
    except Exception:
        pass  # Fall through to whole-string eviction (chonkie missing or chunking failed)

    # Fallback: whole-string eviction (v1.0 behavior)
    eviction_queue.push(
        text=val,
        metadata={"source": f"evicted:{key}", "trace_id": trace_id}
    )
    new_state[key] = f"[Evicted: {token_count} tokens saved to episodic memory. Use memory tool to recall.]"

def node_step(state: WorkflowState, node: str, message: str, checkpoint: bool = False, **kwargs) -> None:
    """Log a workflow step to the active trace.

    This is a HELPER (side-effect only), not a LangGraph node. Returns None.
    """
    tid = state.get("trace_id", "")
    if tid:
        tracer.step(tid, node, message, **kwargs)
    if checkpoint and tid:
        from workflows.helpers.checkpoint import save_checkpoint
        # [v1.2 #1] Save the FULL state, not just {status, error}. This ensures
        # resume from an error checkpoint has the complete workflow context.
        save_checkpoint(tid, node, state)

def node_error(state: WorkflowState, node: str, message: str, **kwargs) -> dict:
    """Mark state as failed and log to trace. Message is never empty.
    Returns a PARTIAL dict (LangGraph best practice — only changed keys).

    [v1.2 #1] Saves the FULL state as checkpoint (was only {status, error}).
    Resume from an error checkpoint now has the complete workflow context.
    """
    if not message or not message.strip():
        message = f"Unspecified error in node '{node}'"
    tid = state.get("trace_id", "")
    if tid:
        tracer.error(tid, node, message, **kwargs)
        from workflows.helpers.checkpoint import save_checkpoint
        # [v1.2 #1] Save full state for resume — was: save_checkpoint(tid, node, {"status": "failed", "error": message})
        save_checkpoint(tid, node, {**state, "status": "failed", "error": message})

    return {"status": "failed", "error": message}

def node_done(state: WorkflowState, result: str, artifacts: list = None) -> dict:
    """Mark state as succeeded.
    Returns a PARTIAL dict (LangGraph best practice — only changed keys).

    [v1.2 #7] Saves a success checkpoint BEFORE mark_complete() so the final
    state is preserved if mark_complete fails or the process dies between them.
    """
    tid = state.get("trace_id", "")
    if tid:
        # [v1.2 #7] Save success checkpoint first (was: no checkpoint on success)
        from workflows.helpers.checkpoint import save_checkpoint
        save_checkpoint(tid, "done", {**state, "status": "success", "result": result})
        tracer.finish(tid, success=True, result=result[:200])
        from workflows.helpers.checkpoint import mark_complete
        mark_complete(tid)
    return {
        "status": "success",
        "result": result,
        "artifacts": artifacts or [],
    }

# -- Workflow dispatcher ------------------------------------------------------
def run_workflow(
    workflow_type: str,
    goal: str,
    trace_id: str = "",
    resume: bool = False,
    **kwargs,
) -> dict:
    """
    Run a named workflow and return the final state as a dict.
    workflow_type : "research" | "data" | "autocode" | "deep_research" | "understand"
    goal          : what to accomplish
    trace_id      : attach to existing trace (creates new one if empty)
    resume        : if True, attempt to restore from checkpoint journal
    **kwargs      : workflow-specific inputs (see each workflow module)

    Returns the final WorkflowState as a plain dict with at minimum:
        {status: "success" | "failed", result: str, error: str, artifacts: list}
    """
    wf_type = workflow_type.strip().lower()

    # Create trace if not provided
    if not trace_id:
        trace_id = tracer.new_trace(wf_type, goal=goal)

    initial_state: WorkflowState = {
        "workflow": wf_type,
        "goal": goal,
        "trace_id": trace_id,
        "retries": 0,
        "status": "running",
        "error": "",
        "result": "",
        "artifacts": [],
        **kwargs,
    }

    # CHECKPOINT RESUMPTION
    restored = None
    if resume:
        from workflows.helpers.checkpoint import get_latest
        restored = get_latest(trace_id)
        if restored:
            if restored.get("_checkpoint_version", 0) != 1:
                tracer.warning(trace_id, "resume", "Checkpoint version mismatch, starting fresh")
            else:
                tracer.step(trace_id, "resume", "Resuming from checkpoint")
                # [v1.2 #5] Don't clobber the checkpoint's original goal.
                # Was: initial_state = {**restored, "status": "running", "goal": goal}
                # If the caller passes a different goal on resume, that overwrites
                # the original — making the checkpoint meaningless. Keep restored goal.
                initial_state = {**restored, "status": "running"}
        else:
            tracer.warning(trace_id, "resume", "No checkpoint found, starting fresh")

    # For autocode workflow, convert goal -> task for compatibility
    if wf_type == "autocode":
        initial_state["task"] = goal

    try:
        if wf_type == "research":
            from workflows.research import build_research_graph
            graph = build_research_graph()
            result = graph.invoke(initial_state)

        elif wf_type == "data":
            from workflows.data import build_data_graph
            graph = build_data_graph()
            result = graph.invoke(initial_state)

        elif wf_type == "autocode":
            from workflows.autocode import build_graph as build_autocode_graph
            # [v1.1] build_graph() returns uncompiled StateGraph — must compile
            # before .invoke(). Was crashing with AttributeError. Also wire
            # invoke_with_timeout so cfg.autocode_graph_timeout is respected.
            from workflows.autocode_impl.graph import invoke_with_timeout
            result = invoke_with_timeout(initial_state)

        elif wf_type == "deep_research":
            from workflows.deep_research_impl import build_deep_research_graph
            graph = build_deep_research_graph()
            result = graph.invoke(initial_state)

        elif wf_type == "understand":
            # [Architecture] Now routes through standard graph.invoke() like all
            # other workflows. Was: run_understand_workflow_sync() with
            # ThreadPoolExecutor + new_event_loop() hack. Now: sync nodes, direct invoke.
            from pathlib import Path
            from workflows.understand import build_understand_graph, _default_state
            from core.kgraph.project import is_same_path

            project_root = initial_state.get("project_root", "")
            is_agent = is_same_path(Path(project_root), cfg.agent_root) if project_root else False
            understand_state = _default_state(project_root, is_agent_root=is_agent, trace_id=trace_id)
            graph = build_understand_graph()
            result = graph.invoke(understand_state)

        else:
            tracer.error(trace_id, "dispatch", f"Unknown workflow type: {wf_type!r}")
            tracer.finish(trace_id, success=False)
            return {
                "status": "failed",
                "error": f"Unknown workflow type '{wf_type}'. Use: research | data | autocode | deep_research | understand",
                "result": "",
                "artifacts": [],
            }

        return dict(result)

    except Exception as e:
        msg = f"Workflow '{wf_type}' crashed: {type(e).__name__}: {e}"
        tracer.error(trace_id, "dispatch", msg)
        # [v1.2 #2] Save checkpoint before returning — was: no checkpoint on crash.
        # State at crash time is now preserved for debugging/resume.
        try:
            from workflows.helpers.checkpoint import save_checkpoint
            save_checkpoint(trace_id, "dispatch_error", {**initial_state, "status": "failed", "error": msg})
        except Exception:
            pass  # Non-fatal: checkpoint failure shouldn't mask the original error
        tracer.finish(trace_id, success=False, result=msg)
        return {
            "status": "failed",
            "error": msg,
            "result": "",
            "artifacts": [],
        }
