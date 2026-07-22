"""workflows/base.py -- Shared state TypedDict, node helpers, and dispatcher.

All six workflows (research, data, autocode, deep_research, understand, autoresearch) share:
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
import threading
from typing import Any, Optional
from typing_extensions import TypedDict
from core.tracer import tracer
from core.config import cfg

# v1.3.1 (P3-3): Extracted constant — used by both trim_state() and trim_state_node().
# v1.3.1 (P2-3): Added 'memory_context' — recalled memories can be large.
_EVICTABLE_FIELDS = ("search_results", "output", "analysis", "memory_context")

# ── Per-workflow cancellation flag ───────────────────────────────────────────
# v1.1-p1 (workflow-v1.1-p1): General-purpose cancellation for ALL workflows.
# Holds trace_ids of workflows that have been cancelled via the cancel action.
# run_workflow() checks is_workflow_cancelled(trace_id) AFTER the dispatch
# returns — for non-autocode workflows the check is post-hoc (graph.invoke()
# is blocking and can't be interrupted from outside). For autocode, the
# existing invoke_with_timeout() + _call() cancellation flag handles
# mid-execution interruption.
_workflow_cancelled: set[str] = set()


def request_workflow_cancel(trace_id: str) -> None:
    """Mark a workflow as cancelled. Idempotent — calling twice is a no-op.

    Called by tools/workflow_ops/actions/cancel.py when the user requests
    cancellation. run_workflow() will check is_workflow_cancelled(trace_id)
    after the dispatch returns and short-circuit with a "cancelled" status
    (saving a checkpoint first so the workflow can be resumed if desired).
    """
    if trace_id:
        _workflow_cancelled.add(trace_id)


def is_workflow_cancelled(trace_id: str) -> bool:
    """Check whether a workflow has been cancelled."""
    return trace_id in _workflow_cancelled


def clear_workflow_cancel(trace_id: str) -> None:
    """Clear the cancellation flag for a trace_id.

    Called by run_workflow() after it has observed the cancellation and
    returned the cancelled status. Ensures a subsequent resume of the same
    trace_id doesn't immediately bail out.
    """
    _workflow_cancelled.discard(trace_id)


# -- Shared workflow state ----------------------------------------------------
class WorkflowState(TypedDict, total=False):
    # Identity
    workflow: str          # "research" | "data" | "autocode" | "deep_research" | "understand" | "autoresearch"
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

    for key in _EVICTABLE_FIELDS:
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


def trim_state_node(state: WorkflowState) -> dict:
    """LangGraph node wrapper for trim_state().

    trim_state() returns a full state dict (Copy-on-Write). LangGraph nodes
    must return PARTIAL dicts (only changed keys). This wrapper calls
    trim_state() and returns only the evicted keys with their new
    placeholder/preview values.

    Used by: data workflow (between critique and store — evicts `output`
    after critique has produced `result`). Other workflows can wire it in
    at their own trim-appropriate points.

    Returns: {} if nothing was evicted, or {"output": "<placeholder>"} etc.
    """
    new_state = trim_state(state)
    # trim_state only modifies evictable fields — return only changed keys
    return {k: new_state[k] for k in _EVICTABLE_FIELDS
            if state.get(k) != new_state.get(k)}


def node_step(state: WorkflowState, node: str, message: str, checkpoint: bool = False, **kwargs) -> None:
    """Log a workflow step to the active trace.

    This is a HELPER (side-effect only), not a LangGraph node. Returns None.
    """
    tid = state.get("trace_id", "")
    if tid:
        tracer.step(tid, node, message, **kwargs)
    if checkpoint and tid:
        from core.observability.checkpoint import save_checkpoint
        # [v1.2 #1] Save the FULL state, not just {status, error}. This ensures
        # resume from an error checkpoint has the complete workflow context.
        # v1.3.1 (P2-2): No status override needed — state is already "running"
        # at this point (node_step is called mid-workflow, not on error/done).
        # node_error and node_done override status to "failed"/"success" respectively.
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
        from core.observability.checkpoint import save_checkpoint
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
        from core.observability.checkpoint import save_checkpoint
        save_checkpoint(tid, "done", {**state, "status": "success", "result": result})
        tracer.finish(tid, success=True, result=result[:200])
        from core.observability.checkpoint import mark_complete
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
    timeout: int = 0,
    **kwargs,
) -> dict:
    """
    Run a named workflow and return the final state as a dict.
    workflow_type : "research" | "data" | "autocode" | "deep_research" | "understand" | "autoresearch"
    goal          : what to accomplish
    trace_id      : attach to existing trace (creates new one if empty)
    resume        : if True, attempt to restore from checkpoint journal
    timeout       : per-workflow timeout in seconds (0 = no timeout, use
                    existing behavior). For non-autocode workflows, wraps the
                    graph.invoke() call with a threading-based deadline. On
                    timeout, saves a checkpoint and returns status="failed"
                    with error="Workflow timed out after {timeout}s". For
                    autocode, this param is IGNORED — autocode manages its
                    own timeout via cfg.autocode_graph_timeout + invoke_with_timeout.
    **kwargs      : workflow-specific inputs (see each workflow module)

    Returns the final WorkflowState as a plain dict with at minimum:
        {status: "success" | "failed", result: str, error: str, artifacts: list}
    """
    wf_type = workflow_type.strip().lower() if workflow_type else ""

    # v1.3.1 (P2-1): Input validation — fail fast before trace creation.
    # Was: empty workflow_type reached the else branch (line ~372) after
    # building initial_state + attempting checkpoint resume. Empty goal was
    # silently accepted — the workflow ran with goal="" producing useless results.
    if not wf_type:
        return {
            "status": "failed",
            "error": "workflow_type is required. Use: research | data | autocode | deep_research | understand | autoresearch",
            "result": "",
            "artifacts": [],
        }
    if not goal or not goal.strip():
        return {
            "status": "failed",
            "error": "goal is required (non-empty)",
            "result": "",
            "artifacts": [],
        }

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
        from core.observability.checkpoint import get_latest
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
                # [v3.4 #38] Merge hitl_approved from kwargs (for HiTL resume)
                if kwargs.get("hitl_approved"):
                    initial_state["hitl_approved"] = True
        else:
            tracer.warning(trace_id, "resume", "No checkpoint found, starting fresh")

    # For autocode workflow, convert goal -> task for compatibility
    if wf_type == "autocode":
        initial_state["task"] = goal

    # v1.1-p1 (workflow-v1.1-p1): Per-workflow timeout + graceful cancel.
    # Build a closure that runs the actual dispatch (the original if/elif
    # chain). For autocode, invoke_with_timeout() manages its own timeout —
    # the `timeout` param is intentionally ignored (autocode uses
    # cfg.autocode_graph_timeout instead). For other workflows, when
    # timeout > 0, we wrap the dispatch in a daemon-thread + join(timeout)
    # pattern (same shape as invoke_with_timeout).
    def _dispatch() -> dict:
        if wf_type == "research":
            from workflows.research import build_research_graph
            graph = build_research_graph()
            return graph.invoke(initial_state)

        elif wf_type == "data":
            from workflows.data import build_data_graph
            graph = build_data_graph()
            return graph.invoke(initial_state)

        elif wf_type == "autocode":
            # [v1.1] build_graph() returns uncompiled StateGraph — must compile
            # before .invoke(). Was crashing with AttributeError. Also wire
            # invoke_with_timeout so cfg.autocode_graph_timeout is respected.
            #
            # v1.1-p1: The `timeout` param is IGNORED for autocode — it manages
            # its own timeout via invoke_with_timeout() + cfg.autocode_graph_timeout
            # (or adaptive per-task-type timeouts when AUTOCODE_ADAPTIVE_TIMEOUT=1).
            from workflows.autocode_impl.graph import invoke_with_timeout
            return invoke_with_timeout(initial_state)

        elif wf_type == "deep_research":
            from workflows.deep_research_impl import build_deep_research_graph
            graph = build_deep_research_graph()
            return graph.invoke(initial_state)

        elif wf_type == "understand":
            # [Architecture] Now routes through standard graph.invoke() like all
            # other workflows. Was: run_understand_workflow_sync() with
            # ThreadPoolExecutor + new_event_loop() hack. Now: sync nodes, direct invoke.
            #
            # [v1.5] `action` parameter routes BEFORE graph construction:
            #   - action="index"  (default) → run the full LangGraph (was: only path).
            #   - action="query"  → call query_codebase() directly (no graph).
            #   - action="health" → call health_check() directly (no graph).
            # The query/health paths skip the is_agent computation + 600s
            # timeout + graph building — they're cheap + don't need any of it.
            # project_root is validated for ALL actions (query/health need a
            # valid path to compute ProjectManager).
            from pathlib import Path
            from core.kgraph.project import is_same_path

            project_root = initial_state.get("project_root", "")
            action = initial_state.get("action", "index")

            # Validate project_root exists for ALL actions — query/health
            # still need a real path to construct ProjectManager + look up
            # kg.db. Fail fast before touching kgraph.
            if not project_root or not Path(project_root).exists():
                return {
                    "status": "failed",
                    "errors": [f"project_root does not exist: {project_root}"],
                    "trace_id": trace_id,
                }

            # ─── action="query" — semantic/keyword/dependencies/callers ──
            if action == "query":
                from workflows.understand_impl.query import query_codebase
                return query_codebase(
                    project_path=project_root,
                    question=goal,  # the search query IS the goal
                    query_type=initial_state.get("query_type", "semantic"),
                    file_path=initial_state.get("file_path", ""),
                    top_k=initial_state.get("top_k", 10),
                    is_agent_root=is_same_path(Path(project_root), cfg.agent_root),
                    trace_id=trace_id,
                )

            # ─── action="health" — index stats (no graph run) ─────────────
            if action == "health":
                from workflows.understand_impl.query import health_check
                return health_check(
                    project_path=project_root,
                    is_agent_root=is_same_path(Path(project_root), cfg.agent_root),
                    trace_id=trace_id,
                )

            # ─── unknown action → fail fast ───────────────────────────────
            if action != "index":
                return {
                    "status": "failed",
                    "errors": [
                        f"Unknown action: {action}. Use: index (default), query, health"
                    ],
                    "trace_id": trace_id,
                }

            # ─── action="index" (default) — run the full graph ────────────
            from workflows.understand import build_understand_graph, _default_state

            is_agent = is_same_path(Path(project_root), cfg.agent_root) if project_root else False
            understand_state = _default_state(project_root, is_agent_root=is_agent, trace_id=trace_id)
            # v1.4: Pass skip_embeddings from initial_state
            if initial_state.get("skip_embeddings"):
                understand_state["skip_embeddings"] = True
            graph = build_understand_graph()
            # v1.4: Run with a 10-minute timeout (was: bare graph.invoke() —
            # could block the MCP channel for minutes on large projects).
            # Uses a daemon thread + result container (same pattern as autocode).
            #
            # v1.1-p1: When the caller passes timeout > 0, the OUTER timeout
            # wrapper in run_workflow() takes precedence — this inner 600s
            # cap still applies as a hard floor. When timeout=0 (default),
            # only the inner 600s cap applies.
            _result_container: list = []
            def _run_understand():
                try:
                    _result_container.append(graph.invoke(understand_state))
                except Exception as e:
                    _result_container.append({"status": "failed", "errors": [str(e)]})
            _t = _threading_local_Thread(target=_run_understand, daemon=True)
            _t.start()
            # [v1.7] Configurable timeout. Was: hardcoded 600s. Now read from
            # cfg.understand_timeout_seconds (env: UNDERSTAND_TIMEOUT_SECONDS,
            # default 600). Lets operators raise for large codebases or lower
            # for small ones (fail faster on stuck graphs).
            _understand_timeout = getattr(cfg, "understand_timeout_seconds", 600)
            _t.join(timeout=_understand_timeout)
            if _t.is_alive():
                return {"status": "failed", "errors": [f"Understand workflow timed out after {_understand_timeout}s — try skip_embeddings=True for graph-only mode"]}
            return _result_container[0] if _result_container else {"status": "failed", "errors": ["Understand workflow returned no result"]}

        elif wf_type == "autoresearch":
            # [v1.0] Autonomous experiment-driven optimization.
            # Evolutionary loop: propose -> modify -> run -> evaluate ->
            # decide -> log -> propose (repeat). Runs indefinitely until
            # human interrupt.
            #
            # [v1.3 P0-1] Loop order changed from evaluate → log → decide
            # to evaluate → decide → log. See graph.py docstring.
            #
            # The default LangGraph recursion_limit (25) is too low for an
            # overnight autoresearch run (each iteration is ~6 node calls).
            # We raise it to a sane default; callers wanting more can pass
            # their own config via run_workflow's **kwargs (none yet —
            # future: accept a recursion_limit kwarg).
            from workflows.autoresearch import build_autoresearch_graph
            from workflows.autoresearch_impl.state import _default_state as _ar_default
            ar_state = _ar_default(
                goal=goal,
                trace_id=trace_id,
                project_root=initial_state.get("project_root", ""),
                target_file=initial_state.get("target_file", ""),
                metric_name=initial_state.get("metric_name", ""),
                metric_direction=initial_state.get("metric_direction", ""),
                time_budget=initial_state.get("time_budget"),
                branch=initial_state.get("branch", ""),
                results_path=initial_state.get("results_path", ""),
                max_iterations=initial_state.get("max_iterations", 0),
                parallel_count=initial_state.get("parallel_count", 1),
                # [v1.8 / autoresearch v1.11 A8] Forward the 3 loop-control
                # knobs that were previously state fields but NOT forwarded
                # by the type handler / dispatcher. reflect_interval was
                # cfg-only (not a state field at all pre-v1.11);
                # convergence_window + convergence_epsilon were state fields
                # but the type handler didn't forward them, so per-call
                # overrides were silently dropped.
                reflect_interval=initial_state.get("reflect_interval", 0),
                convergence_window=initial_state.get("convergence_window", 10),
                convergence_epsilon=initial_state.get("convergence_epsilon", 0.001),
            )
            # Merge any extra kwargs the caller passed (e.g. dry_run, overrides)
            ar_state.update({k: v for k, v in initial_state.items()
                             if k not in ar_state or ar_state.get(k) in ("", None, 0, 0.0)})

            # [v1.7 N3] If resuming, restore from checkpoint (overrides the
            # _ar_default fresh state). The top-level checkpoint resume code
            # already runs `initial_state = {**restored, ...}` for all workflow
            # types, but autoresearch needs the explicit merge here because:
            #   (a) ar_state["resume"] must be set to True so node_setup's
            #       resume path activates (skip baseline + branch creation).
            #   (b) Only autoresearch-specific fields are merged in — caller
            #       params (goal, target_file, etc.) are preserved as-is from
            #       _ar_default (which already pulled them from initial_state).
            #   (c) The "no checkpoint found" case is traced explicitly so
            #       operators know a resume request fell back to a fresh start.
            if resume:
                from core.observability.checkpoint import get_latest
                restored = get_latest(trace_id)
                if restored:
                    tracer.step(trace_id, "dispatch", "autoresearch: resuming from checkpoint")
                    # Merge restored state (experiment_count, current_best,
                    # history, etc.) but keep the caller's params (goal,
                    # target_file, etc.) which _ar_default already set.
                    for key in ("experiment_count", "current_best", "baseline_metric",
                                "experiment_history", "branch", "results_path",
                                "reflect_notes", "baseline_established"):
                        if key in restored:
                            ar_state[key] = restored[key]
                    ar_state["resume"] = True
                else:
                    tracer.warning(
                        trace_id, "dispatch",
                        "autoresearch: no checkpoint found, starting fresh",
                    )

            graph = build_autoresearch_graph()
            # Default to 1000 iterations (~6000 node calls) — enough for an
            # overnight run. Callers wanting more should invoke the graph
            # directly with their own recursion_limit.
            #
            # [v1.3 P0-2] GraphRecursionError is the EXPECTED exit for the
            # autoresearch loop (it's an evolutionary infinite loop — the
            # recursion_limit is the only safety cap). Was: caught by the
            # generic `except Exception` in run_workflow, returning
            # {"status": "failed"} — discarding all accumulated state
            # (experiment_count, current_best, experiment_history). Now
            # caught explicitly here and returned as {"status": "success"}
            # with the trace_id; operators inspect results.tsv for the
            # experiment count + best metric.
            try:
                # [v1.9 D3] Read recursion_limit from cfg (env-overridable via
                # AUTORESEARCH_RECURSION_LIMIT, default 1000). Was: hardcoded
                # 1000 — operators couldn't raise it for long overnight runs.
                # (minimax Risk #2)
                _ar_recursion_limit = int(getattr(cfg, "autoresearch_recursion_limit", 1000))
                return graph.invoke(
                    ar_state,
                    config={"recursion_limit": _ar_recursion_limit},
                )
            except Exception as e:
                # String-match to avoid a hard dependency on
                # langgraph.errors.GraphRecursionError (import path varies
                # across langgraph versions).
                if "Recursion" in type(e).__name__ or "recursion" in str(e).lower():
                    tracer.step(
                        trace_id, "dispatch",
                        "Recursion limit reached (expected for autoresearch) — "
                        "see results.tsv for experiment count + best metric",
                    )
                    return {
                        "status": "success",
                        "result": (
                            "Recursion limit reached — check results.tsv for "
                            "experiment count and best metric"
                        ),
                        "trace_id": trace_id,
                        "experiment_count": ar_state.get("experiment_count", 0),
                        "current_best": ar_state.get("current_best", 0.0),
                    }
                raise

        else:
            tracer.error(trace_id, "dispatch", f"Unknown workflow type: {wf_type!r}")
            tracer.finish(trace_id, success=False)
            return {
                "status": "failed",
                "error": f"Unknown workflow type '{wf_type}'. Use: research | data | autocode | deep_research | understand | autoresearch",
                "result": "",
                "artifacts": [],
            }

    try:
        # ── Dispatch with optional timeout wrapper ──────────────────────────
        # Autocode manages its own timeout via invoke_with_timeout — never
        # wrap it. For other workflows, wrap in a daemon-thread + join when
        # timeout > 0 (same pattern as invoke_with_timeout).
        if wf_type == "autocode" or timeout <= 0:
            result = _dispatch()
        else:
            result = _run_with_timeout(_dispatch, timeout, trace_id, initial_state)

        # ── Post-dispatch cancellation check ────────────────────────────────
        # For non-autocode workflows, graph.invoke() is blocking — we can't
        # interrupt it mid-execution. We check the cancel flag AFTER it returns
        # and short-circuit with a "cancelled" status if the user requested
        # cancellation while the workflow was running.
        if is_workflow_cancelled(trace_id):
            from core.observability.checkpoint import save_checkpoint
            try:
                save_checkpoint(
                    trace_id, "cancelled",
                    {**initial_state, "status": "cancelled", "error": "Workflow cancelled by user"},
                )
            except Exception:
                pass  # Non-fatal
            clear_workflow_cancel(trace_id)
            tracer.step(trace_id, "dispatch", "Workflow cancelled by user request")
            return {
                "status": "cancelled",
                "error": "Workflow cancelled by user",
                "result": "",
                "artifacts": [],
                "trace_id": trace_id,
            }

        return dict(result)

    except Exception as e:
        msg = f"Workflow '{wf_type}' crashed: {type(e).__name__}: {e}"
        tracer.error(trace_id, "dispatch", msg)
        # [v1.2 #2] Save checkpoint before returning — was: no checkpoint on crash.
        # State at crash time is now preserved for debugging/resume.
        try:
            from core.observability.checkpoint import save_checkpoint
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


def _run_with_timeout(
    dispatch_fn,
    timeout: int,
    trace_id: str,
    initial_state,
) -> dict:
    """Run dispatch_fn() in a daemon thread with a timeout deadline.

    Mirrors the invoke_with_timeout pattern from workflows.autocode_impl.graph:
    start a daemon thread, join(timeout), and if the thread is still alive
    treat it as a timeout — save a checkpoint and return a "timed out" status.

    The daemon thread can't be killed (Python limitation) — it will exit on
    its own when the process exits or when the underlying graph.invoke()
    returns. This matches the autocode behavior.

    Args:
        dispatch_fn: Zero-arg callable that runs the actual dispatch.
        timeout: Timeout in seconds.
        trace_id: Trace ID for checkpoint + tracer logging.
        initial_state: WorkflowState dict — saved as checkpoint on timeout.

    Returns:
        Result dict from dispatch_fn, or a "timed out" failure dict.
    """
    result_container: list = []
    invoke_error: Exception | None = None

    def _run():
        nonlocal invoke_error
        try:
            result_container.append(dispatch_fn())
        except Exception as e:
            invoke_error = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if invoke_error is not None:
        # Surface the inner exception — without this, the caller sees a
        # generic "timed out" error when the graph actually crashed.
        raise invoke_error

    if thread.is_alive():
        # Timeout fired — save a checkpoint so the workflow can be resumed.
        from core.observability.checkpoint import save_checkpoint
        try:
            save_checkpoint(
                trace_id, "timeout",
                {**initial_state, "status": "failed", "error": f"Workflow timed out after {timeout}s"},
            )
        except Exception:
            pass  # Non-fatal
        tracer.error(trace_id, "dispatch", f"Workflow timed out after {timeout}s")
        return {
            "status": "failed",
            "error": f"Workflow timed out after {timeout}s",
            "result": "",
            "artifacts": [],
            "trace_id": trace_id,
        }

    if not result_container:
        return {
            "status": "failed",
            "error": "Workflow returned no result",
            "result": "",
            "artifacts": [],
            "trace_id": trace_id,
        }

    return result_container[0]


# Local alias so the understand branch's threading usage doesn't add a new
# top-level import (keeps the diff minimal — `threading` is already imported
# at module level for the timeout wrapper).
_threading_local_Thread = threading.Thread
