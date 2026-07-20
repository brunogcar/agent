"""Graph builder and metadata for the autoresearch workflow.

[v1.0] Builds the LangGraph state machine for autoresearch:

    setup → propose → modify → run_experiment → evaluate → decide → log → propose (loop)

[v1.3 P0-1] Graph order swapped from `evaluate → log → decide` to
`evaluate → decide → log`. The OLD order was broken: `log` read
`proposal.get("status")` BEFORE `decide` set it → the ledger ALWAYS said
"discard" (even for keeps). The NEW order lets `decide` annotate
`current_experiment` with `status` + `commit` first, then `log` writes
the annotated dict to the ledger.

[v1.3 P2-5] `route_after_evaluate` and `route_after_decide` (both
unconditional single-destination "fake" conditionals) have been replaced
with direct `add_edge(...)` calls. Only `route_after_setup` remained
conditional (it has real branching: success → propose, failure → END).

[v1.4] The `log → propose` back-edge changed from a direct edge back to a
conditional edge — `route_after_log` checks 3 stopping conditions:
  1. max_iterations reached (caller-set hard cap; 0 = unlimited).
  2. Convergence: last N experiments all discarded (no improvement).
  3. Stuck: last N experiments all have metric within ε of current_best.
All three are OFF by default — v1.4 preserves v1.3's "loop forever"
behavior unless a caller opts in.

The experiment loop runs indefinitely (v1.3 behavior) or until a stopping
condition is met (v1.4 opt-in). LangGraph's recursion_limit is still the
ultimate safety cap — callers should set a high limit (or use
invoke_with_recursion_limit) when running overnight.

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
from workflows.autoresearch_impl.routes import route_after_setup, route_after_log


# [WORKFLOW_METADATA] Structured metadata for MCP client introspection.
# Allows clients (and humans) to render the workflow structure without
# reading source code. Mirrors the schema used by research / autocode /
# deep_research / understand / data.
WORKFLOW_METADATA = {
    "name": "autoresearch",
    "version": "1.4",  # [v1.4] loop control (max_iterations + convergence + stuck + dedup)
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
                "commit (keep) + annotate current_experiment, else → git "
                "reset --hard (discard). Resets status to 'running' so the "
                "next iteration starts clean (v1.3 P0-1)."
            ),
        },
        {
            "name": "log",
            "type": "logic",
            "description": (
                "Append the annotated experiment (post-decide) to results.tsv "
                "(tab-separated: iteration, commit, metric, status, description) "
                "and update experiment_history. Reads current_experiment.status "
                "+ commit set by decide (v1.3 P0-1 — was reading pre-decide "
                "values, so ledger always said 'discard'). [v1.4] Stores "
                "content_hash on the history entry for dedup."
            ),
        },
    ],
    "edges": [
        {
            "from": "setup",
            "to": "propose",
            "condition": "route_after_setup: success → propose, failure → END",
        },
        {"from": "propose", "to": "modify"},
        {"from": "modify", "to": "run_experiment"},
        {"from": "run_experiment", "to": "evaluate"},
        # [v1.3 P0-1 + P2-5] Direct edge — was a fake conditional (route_after_evaluate).
        # Order changed from evaluate → log → decide to evaluate → decide → log
        # so that decide can annotate current_experiment BEFORE log reads it.
        {"from": "evaluate", "to": "decide"},
        {"from": "decide", "to": "log"},
        # [v1.4] Conditional edge — was a direct edge in v1.3.
        # route_after_log checks max_iterations + convergence + stuck before
        # looping back to propose. All conditions default OFF (max_iterations=0,
        # window large, ε small) so v1.4 preserves v1.3 "loop forever" behavior
        # unless a caller opts in.
        {
            "from": "log",
            "to": "propose",
            "condition": (
                "route_after_log: continue → propose, stop → END "
                "(max_iterations / convergence / stuck; all default OFF)"
            ),
            "type": "loop",
        },
    ],
    "loops": [
        {
            "name": "experiment_loop",
            "nodes": [
                "propose", "modify", "run_experiment",
                "evaluate", "decide", "log",
            ],
            "exit_condition": (
                "human interrupt OR recursion_limit OR "
                "[v1.4] max_iterations / convergence / stuck"
            ),
            "max_iterations": "unlimited (v1.4 opt-in: caller-set max_iterations)",
        },
    ],
    "branches": [],
    "safety_features": [
        "git_branch",          # all experiments isolated on autoresearch/{tag}
        "results_ledger",      # every experiment logged to results.tsv
        "time_budget",         # each experiment run is time-boxed
        "atomic_writes",       # modify node uses tempfile + os.replace
        "git_reset_on_discard",  # worse experiments rolled back to HEAD
        "path_traversal_guard",  # [v1.3 P1-3] modify node blocks ../ escapes
        "protected_file_guard",  # [v1.3 P1-3] modify node blocks cfg.protected list
        "git_reset_safety",       # [v1.3 P1-4] _git_reset_hard refuses no-root / non-repo
        "max_iterations",         # [v1.4] caller-set hard cap (0=unlimited)
        "convergence_detector",   # [v1.4] stop after N consecutive discards
        "stuck_detector",         # [v1.4] stop on metric plateau (within ε of best)
        "experiment_dedup",       # [v1.4 N8] md5 hash check on new_content
    ],
}


def build_autoresearch_graph():
    """Build and compile the autoresearch workflow graph.

    Returns a compiled LangGraph that can be .invoke()'d with an
    AutoresearchState dict.

    [v1.3 P0-1] Graph order is `evaluate → decide → log → propose`.
    The OLD order (`evaluate → log → decide`) was broken — `log` read
    `current_experiment.status` BEFORE `decide` annotated it, so the
    ledger ALWAYS recorded "discard" (even for keeps). `decide` now
    annotates first, then `log` writes the correct status.

    [v1.3 P2-5] `route_after_evaluate` and `route_after_decide` (both
    unconditional single-destination "fake" conditionals) replaced with
    direct edges. Only `route_after_setup` is conditional (real branching).

    [v1.4] The `log → propose` back-edge changed from a direct edge back to
    a conditional edge — `route_after_log` checks 3 stopping conditions
    (max_iterations / convergence / stuck). All default OFF so v1.4 preserves
    v1.3's "loop forever" behavior unless a caller opts in.

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
    # v1.2.1 (P1-1): Conditional edge after setup — routes to END on failure
    # (was: linear edge that let setup failures spin the loop infinitely).
    g.add_conditional_edges(
        "setup",
        route_after_setup,
        {"propose": "propose", "end": END},
    )
    g.add_edge("propose", "modify")
    g.add_edge("modify", "run_experiment")
    g.add_edge("run_experiment", "evaluate")

    # [v1.3 P0-1 + P2-5] evaluate → decide (was: evaluate → log).
    # Was a fake conditional (route_after_evaluate always returned "log").
    # Now a direct edge; decide annotates current_experiment before log reads it.
    g.add_edge("evaluate", "decide")

    # [v1.3 P0-1 + P2-5] decide → log (was: log → decide).
    # Was a fake conditional (route_after_decide always returned "propose").
    # Now a direct edge; decide runs first to annotate current_experiment
    # with {status, commit}, then log writes the annotated dict to the ledger.
    g.add_edge("decide", "log")

    # [v1.4] Conditional edge after log — replaces the v1.3 direct edge.
    # route_after_log checks max_iterations + convergence + stuck before
    # looping back to propose. All 3 conditions default OFF (max_iterations=0,
    # window large, ε small) so v1.4 preserves v1.3 "loop forever" behavior
    # unless a caller opts in via run_workflow(max_iterations=...) or env vars.
    g.add_conditional_edges(
        "log",
        route_after_log,
        {"propose": "propose", "end": END},
    )

    return g.compile()
