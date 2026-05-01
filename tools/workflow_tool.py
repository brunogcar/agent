"""
tools/workflow_tool.py -- Workflow meta-tool.

Exposes the three LangGraph workflows as a single MCP tool.
The LLM sees ONE tool: workflow(type, goal, ...)

Types:
  research  -> recall->search->synthesize->store->notify
  data      -> recall->execute->critique->store->notify
  autocode  -> snapshot->read->recall->analyze->code->
               review->syntax->apply->test->commit/rollback->
               store_learning->notify
"""

from __future__ import annotations

from registry import tool


@tool
def workflow(
    type:         str,
    goal:         str,
    # data workflow
    code:         str = "",
    # autocode workflow
    target_file:  str = "",
    mode:         str = "improve",
    error_msg:    str = "",
    feature_desc: str = "",
    trace_id:     str = "",
) -> dict:
    """
    Workflow tool -- run a multi-step autonomous workflow.

    type: "research" | "data" | "autocode"

    -- RESEARCH -----------------------------------------------------------------
    Multi-step information gathering and synthesis.
    Pattern: recall -> web search -> scrape -> synthesize -> store -> notify

    goal     : what to research (e.g. "ChromaDB best practices for production")
    trace_id : optional -- attach to existing trace

    Returns: {status, result (full synthesis), artifacts}

    Example:
        workflow(type="research",
                 goal="What are the best practices for FastMCP tool design?")

    -- DATA ---------------------------------------------------------------------
    Data analysis and calculation workflow.
    Pattern: recall -> execute Python -> critique output -> store -> notify

    goal : what to analyse
    code : Python code to run (optional -- executor will generate if not provided)
           Always use print() for output.

    Returns: {status, result (output + analysis), artifacts}

    Examples:
        workflow(type="data",
                 goal="Calculate monthly growth rates from the sales data",
                 code="import pandas as pd\\ndf = pd.read_csv('sales.csv')\\n...")

        workflow(type="data",
                 goal="Generate a summary of the Q3 results")
        # (code omitted -- executor generates it)

    -- AUTOCODE -----------------------------------------------------------------
    Autonomous code editing with safety guards.
    Pattern: git snapshot -> read file -> recall patterns ->
             analyze -> generate patch -> review (CODER/REVIEWER/ANALYZER) ->
             syntax check -> apply -> test -> commit OR rollback ->
             store learning -> notify

    ALWAYS uses git snapshot first. Rolls back automatically on failure.
    NEVER touches protected files: server.py, registry.py, core/config.py,
    core/tracer.py.

    target_file  : path relative to agent root (e.g. "tools/memory_tool.py")
    mode         : "fix_error"   -- fix a specific error (requires error_msg)
                   "improve"     -- refactor/improve code (requires goal)
                   "add_feature" -- add new functionality (requires feature_desc)
    goal         : what to accomplish
    error_msg    : the error traceback (for fix_error mode)
    feature_desc : description of feature to add (for add_feature mode)

    Returns: {status, result (commit message or error), artifacts (files + commits)}

    Examples:
        workflow(type="autocode",
                 mode="fix_error",
                 target_file="tools/web.py",
                 goal="Fix the timeout error in scrape",
                 error_msg="TimeoutException: Timeout fetching https://...")

        workflow(type="autocode",
                 mode="improve",
                 target_file="memory/store.py",
                 goal="Add input validation to store_semantic()")

        workflow(type="autocode",
                 mode="add_feature",
                 target_file="tools/file_ops.py",
                 goal="Add CSV reading support",
                 feature_desc="read_csv action that parses CSV and returns list of dicts")
    """
    wf_type = type.strip().lower()

    if wf_type not in ("research", "data", "autocode"):
        return {
            "status": "error",
            "error":  (
                f"Unknown workflow type '{wf_type}'. "
                "Use: research | data | autocode"
            ),
        }

    if not goal:
        return {"status": "error", "error": "goal is required"}

    if wf_type == "autocode":
        if not target_file:
            return {"status": "error",
                    "error": "target_file is required for autocode"}
        if mode == "fix_error" and not error_msg:
            return {"status": "error",
                    "error": "error_msg is required for mode='fix_error'"}
        if mode == "add_feature" and not feature_desc:
            return {"status": "error",
                    "error": "feature_desc is required for mode='add_feature'"}

    # Lazy import -- workflows import langgraph which is moderately heavy
    from workflows.base import run_workflow

    kwargs = {}
    if wf_type == "data":
        if code:
            kwargs["code"] = code
    elif wf_type == "autocode":
        kwargs.update({
            "target_file":  target_file,
            "mode":         mode,
            "error_msg":    error_msg,
            "feature_desc": feature_desc,
        })
    if trace_id:
        kwargs["trace_id"] = trace_id

    return run_workflow(
        workflow_type = wf_type,
        goal          = goal,
        **kwargs,
    )
