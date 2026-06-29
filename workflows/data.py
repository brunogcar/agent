"""
workflows/data.py -- Data analysis workflow.

Pattern:
  recall -> execute -> critique -> store -> notify

For: pandas/numpy analysis, calculations, dataset generation.

Usage:
    from workflows.base import run_workflow

    result = run_workflow(
        workflow_type = "data",
        goal          = "Analyse monthly sales and find the top 3 months",
        code          = "import pandas as pd\ndf = pd.read_csv('sales.csv')\nprint(df.groupby('month')['revenue'].sum().nlargest(3))",
    )
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from workflows.base import WorkflowState, node_step, node_error, node_done


# -- Nodes --------------------------------------------------------------------

def node_recall(state: WorkflowState) -> WorkflowState:
    """Check memory for relevant prior analysis or patterns."""
    from core.memory import memory

    goal = state.get("goal", "")
    node_step(state, "recall", "checking memory", goal=goal[:60])

    results = memory.recall(
        query=goal, top_k=3,
        trace_id=state.get("trace_id", ""),
    )

    ctx = ""
    if results:
        ctx = "\n".join(
            f"[{r['type']}] {r['text']}"
            for r in results
        )
        node_step(state, "recall", f"found {len(results)} relevant memories")
    else:
        node_step(state, "recall", "no prior context found")

    return {**state, "memory_context": ctx}


def node_execute(state: WorkflowState) -> WorkflowState:
    """Execute the provided Python code.

    If no code is provided, delegates to agent(role="code") to generate
    Python code from the goal. The code role returns structured JSON with
    {analysis, patch, assumptions, tests} — we extract the "patch" field.
    """
    from tools.python_exec import python

    code = state.get("code", "")
    goal = state.get("goal", "")

    if not code:
        # No code provided -- ask executor to generate it
        from tools.agent import agent  # [PHASE-3] Migrated from tools.agent_tool ? tools.agent
        node_step(state, "execute", "no code provided -- generating")

        r = agent(
            role     = "code",
            task     = f"Write Python code to: {goal}. Use print() for all output.",
            context  = state.get("memory_context", ""),
            trace_id = state.get("trace_id", ""),
        )
        if r.get("status") != "success":
            return node_error(state, "execute",
                              f"Code generation failed: {r.get('error', 'unknown')}")

        # Extract code from structured response
        parsed = r.get("parsed", {})
        if parsed and "patch" in parsed:
            code = parsed["patch"]
        else:
            # Try to extract code block from text
            text = r.get("text", "")
            import re
            match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
            code  = match.group(1) if match else text

    node_step(state, "execute", "running code", chars=len(code))
    result = python(mode="run_data", code=code)

    if result.get("status") != "success":
        error = result.get("error", "unknown error")
        node_step(state, "execute", f"execution failed: {error[:100]}")
        return {**state, "exec_error": error, "output": ""}

    output = result.get("output", "(no output)")
    node_step(state, "execute", "execution successful",
              output_chars=len(output))
    return {**state, "output": output, "exec_error": "", "code": code}


def node_critique(state: WorkflowState) -> WorkflowState:
    """Have the executor critique the output quality.

    Uses agent(role="critique") to evaluate whether the code output
    adequately answers the user's goal. The critique role has a 90s
    timeout and returns free-form Markdown (not JSON).
    """
    from tools.agent import agent  # thin facade; prompts/roles live in agent_ops/  # [PHASE-3] Migrated from tools.agent_tool ? tools.agent

    output = state.get("output", "")
    goal   = state.get("goal", "")

    if not output:
        return state

    node_step(state, "critique", "evaluating output quality")

    r = agent(
        role    = "critique",
        task    = f"Does this output adequately answer: '{goal}'? "
                  "Note any missing analysis, errors, or improvements.",
        content = f"Code output:\n{output[:1000]}",
        trace_id= state.get("trace_id", ""),
    )

    if r.get("status") == "success":
        node_step(state, "critique", "critique complete")
        # Append critique to result
        full_result = f"OUTPUT:\n{output}\n\nANALYSIS:\n{r['text']}"
        return {**state, "result": full_result}

    # Critique failed -- just use output as-is
    return {**state, "result": output}


def node_store(state: WorkflowState) -> WorkflowState:
    """Store analysis results in episodic memory."""
    from core.memory import memory

    goal   = state.get("goal", "")
    result = state.get("result", "") or state.get("output", "")
    code   = state.get("code", "")

    if not result:
        return state

    node_step(state, "store", "saving results to memory")

    memory.store_episodic(
        text       = f"Data analysis: '{goal[:60]}'\nResult: {result[:400]}",
        importance = 6,
        goal       = goal,
        outcome    = "success",
        tools_used = "python,agent,memory",
        trace_id   = state.get("trace_id", ""),
    )

    # If code worked well, store as procedural
    if code and result:
        memory.store_procedural(
            text       = f"Working data code for '{goal[:60]}':\n{code[:400]}",
            importance = 6,
            tags       = "data,python,working-code",
            trace_id   = state.get("trace_id", ""),
        )

    return state


def node_notify(state: WorkflowState) -> WorkflowState:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from workflows.base import node_done

    goal   = state.get("goal", "")
    result = state.get("result", "") or state.get("output", "")

    notify(
        action  = "send",
        title   = "Data analysis complete",
        message = f"{goal[:50]}: {result[:80]}",
    )
    return node_done(state, result=result or "Data analysis complete")


# -- Routing ------------------------------------------------------------------

def route_after_execute(state: WorkflowState) -> str:
    if state.get("exec_error"):
        return "failed"
    return "critique"


def route_after_critique(state: WorkflowState) -> str:
    return "store"


# -- Graph builder ------------------------------------------------------------

def build_data_graph() -> StateGraph:
    """Build and compile the data workflow graph."""
    g = StateGraph(WorkflowState)

    g.add_node("recall",   node_recall)
    g.add_node("execute",  node_execute)
    g.add_node("critique", node_critique)
    g.add_node("store",    node_store)
    g.add_node("notify",   node_notify)

    g.set_entry_point("recall")

    g.add_edge("recall", "execute")

    g.add_conditional_edges(
        "execute",
        route_after_execute,
        {"critique": "critique", "failed": END},
    )

    g.add_edge("critique", "store")
    g.add_edge("store",    "notify")
    g.add_edge("notify",   END)

    return g.compile()

