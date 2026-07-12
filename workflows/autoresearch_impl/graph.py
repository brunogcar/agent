"""Graph builder and metadata for the autoresearch workflow.

[v1.0] Builds the LangGraph state machine for autoresearch:

    setup → propose → modify → run_experiment → evaluate → decide → log → propose (loop)

The experiment loop runs indefinitely until a human interrupts the process.
LangGraph's recursion_limit caps the number of iterations per invocation —
callers should set a high limit (or use invoke_with_recursion_limit) when
running overnight.

WORKFLOW_METADATA mirrors the structure used by autocode_impl/graph.py
(the most complex existing workflow): name, version, description,
entry_point, nodes, edges, loops, branches (empty for v1.0), safety_features.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.nodes.setup import node_setup
from workflows.autoresearch_impl.nodes.propose import node_propose
from workflows.autoresearch_impl.nodes.modify import node_modify
from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
from workflows.autoresearch_impl.nodes.evaluate import node_evaluate
from workflows.autoresearch_impl.nodes.decide import node_decide
from workflows.autoresearch_impl.nodes.log import node_log
from workflows.autoresearch_impl.routes import (
    route_after_evaluate,
    route_after_decide,
)


# [WORKFLOW_METADATA] Structured metadata for MCP client introspection.
# Allows clients (and humans) to render the workflow structure without
# reading source code. Mirrors the schema used by research / autocode /
# deep_research / understand / data.
WORKFLOW_METADATA = {
    "name": "autoresearch",
    "version": "1.0",
    "description": (
        "Autonomous experiment-driven optimization: "
        "modify → run → measure → keep/discard → repeat"
    ),
    "entry_point": "setup",
    "nodes": [
        {
            "name": "setup",
            "type": "tool",
            "tool": "git+subprocess",
            "description": (
                "Create git branch autoresearch/{tag}, initialize results.tsv, "
                "run baseline experiment, record baseline metric"
            ),
        },
        {
            "name": "propose",
            "type": "llm",
            "role": "planner",
            "description": (
                "LLM proposes the next experiment (description + rationale + "
                "new_content) based on history and current best metric"
            ),
        },
        {
            "name": "modify",
            "type": "tool",
            "tool": "file",
            "description": (
                "Apply the proposed new_content to target_file via atomic "
                "tempfile + os.replace write"
            ),
        },
        {
            "name": "run_experiment",
            "type": "tool",
            "tool": "subprocess",
            "description": (
                "Execute target_file as a time-boxed subprocess "
                "(time_budget seconds), capture stdout+stderr"
            ),
        },
        {
            "name": "evaluate",
            "type": "logic",
            "description": (
                "Extract metric from experiment output via regex "
                "({metric_name}: <float>), take the last occurrence"
            ),
        },
        {
            "name": "decide",
            "type": "tool",
            "tool": "git",
            "description": (
                "Compare current_metric vs current_best; if improved → git "
                "commit (keep), else → git reset --hard (discard)"
            ),
        },
        {
            "name": "log",
            "type": "logic",
            "description": (
                "Append result row to results.tsv (tab-separated: iteration, "
                "commit, metric, status, description) and update "
                "experiment_history"
            ),
        },
    ],
    "edges": [
        {"from": "setup", "to": "propose"},
        {"from": "propose", "to": "modify"},
        {"from": "modify", "to": "run_experiment"},
        {"from": "run_experiment", "to": "evaluate"},
        {
            "from": "evaluate",
            "to": "log",
            "condition": "route_after_evaluate: always log (complete ledger)",
        },
        {"from": "log", "to": "decide"},
        {
            "from": "decide",
            "to": "propose",
            "condition": "route_after_decide: always loop (runs until human interrupt)",
            "type": "loop",
        },
    ],
    "loops": [
        {
            "name": "experiment_loop",
            "nodes": [
                "propose", "modify", "run_experiment",
                "evaluate", "log", "decide",
            ],
            "exit_condition": "human interrupt",
            "max_iterations": "unlimited (runs until stopped)",
        },
    ],
    "branches": [],
    "safety_features": [
        "git_branch",          # all experiments isolated on autoresearch/{tag}
        "results_ledger",      # every experiment logged to results.tsv
        "time_budget",         # each experiment run is time-boxed
        "atomic_writes",       # modify node uses tempfile + os.replace
        "git_reset_on_discard",  # worse experiments rolled back to HEAD
    ],
}


def build_autoresearch_graph():
    """Build and compile the autoresearch workflow graph.

    Returns a compiled LangGraph that can be .invoke()'d with an
    AutoresearchState dict. The compiled graph includes a conditional edge
    from decide → propose that creates the infinite experiment loop.

    Callers should pass a high recursion_limit when invoking, e.g.:

        graph.invoke(initial_state, config={"recursion_limit": 1000})

    LangGraph's default recursion_limit (25) is too low for an overnight run.
    """
    g = StateGraph(AutoresearchState)

    # Add all 7 nodes
    g.add_node("setup", node_setup)
    g.add_node("propose", node_propose)
    g.add_node("modify", node_modify)
    g.add_node("run_experiment", node_run_experiment)
    g.add_node("evaluate", node_evaluate)
    g.add_node("decide", node_decide)
    g.add_node("log", node_log)

    # Entry point
    g.set_entry_point("setup")

    # Linear edges: setup → propose → modify → run_experiment → evaluate
    g.add_edge("setup", "propose")
    g.add_edge("propose", "modify")
    g.add_edge("modify", "run_experiment")
    g.add_edge("run_experiment", "evaluate")

    # After evaluate: always go to log (we log every experiment, even failures)
    g.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {"log": "log"},
    )

    # log → decide (decide reads current_metric + current_best and either
    # commits or resets)
    g.add_edge("log", "decide")

    # After decide: always loop back to propose (infinite loop until human
    # interrupt). This is the core of the autoresearch workflow.
    g.add_conditional_edges(
        "decide",
        route_after_decide,
        {"propose": "propose"},
    )

    return g.compile()
