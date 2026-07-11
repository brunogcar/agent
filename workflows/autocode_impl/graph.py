"""
State machine construction for autocode workflow.

v1.1: Added WORKFLOW_METADATA for MCP client introspection. Includes
explicit loops array (debug loop) and branches array (create_skill bypass)
so MCP clients can render the graph correctly.
"""
from __future__ import annotations
from langgraph.graph import END, StateGraph
from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.nodes.classify import node_classify_task
from workflows.autocode_impl.nodes.validate import node_validate_input
from workflows.autocode_impl.nodes.brainstorm import node_brainstorm
from workflows.autocode_impl.nodes.plan import node_write_plan
from workflows.autocode_impl.nodes.branch import node_git_branch
from workflows.autocode_impl.nodes.tests import node_write_tests
from workflows.autocode_impl.nodes.execute import node_execute_step
from workflows.autocode_impl.nodes.run_tests import node_run_tests
from workflows.autocode_impl.nodes.analyze_impact import node_analyze_impact
from workflows.autocode_impl.nodes.debug import node_systematic_debug
from workflows.autocode_impl.nodes.write_files import (
    node_write_files,
    node_write_files_with_flag_reset,
)
from workflows.autocode_impl.nodes.verify import node_verify
from workflows.autocode_impl.nodes.commit import node_commit
from workflows.autocode_impl.nodes.publish import node_publish  # [v1.3]
from workflows.autocode_impl.nodes.memory import node_distill_memory
from workflows.autocode_impl.nodes.create_skill import node_create_skill
from workflows.autocode_impl.nodes.report import node_report
from workflows.autocode_impl.routes import (
    route_after_classify,
    route_after_run_tests,
    route_after_write_files,
    route_after_verify,
    route_after_analyze_impact,
)


# [v1.1] WORKFLOW_METADATA for MCP client introspection.
# Pragmatic schema: nodes (with type), edges (with condition + loop flag),
# explicit loops array, explicit branches array. Mirrors the pattern in
# research/understand/data/deep_research but extended for autocode's
# complexity (17 nodes, debug loop, create_skill bypass).
WORKFLOW_METADATA = {
    "name": "autocode",
    "version": "1.3",  # [v1.3] GitHub + Swarm integration
    "description": "Autonomous coding with TDD, debug loops, impact analysis, git integration, and procedural memory",
    "entry_point": "node_classify_task",
    "nodes": [
        {"name": "node_classify_task", "type": "llm", "role": "router", "description": "Classify task type from goal"},
        {"name": "node_validate_input", "type": "logic", "description": "Validate input files and path safety"},
        {"name": "node_brainstorm", "type": "llm", "role": "planner", "description": "Brainstorm spec tailored to task type"},
        {"name": "node_write_plan", "type": "llm", "role": "planner", "description": "Write structured plan with acceptance criteria"},
        {"name": "node_git_branch", "type": "tool", "tool": "git", "description": "Create git branch for the task"},
        {"name": "node_write_tests", "type": "llm", "role": "executor", "description": "Write TDD tests before implementation"},
        {"name": "node_execute_step", "type": "llm", "role": "executor", "description": "Generate implementation code from plan"},
        {"name": "node_write_files", "type": "tool", "tool": "file", "description": "Write generated code to disk atomically"},
        {"name": "node_write_files_with_flag_reset", "type": "tool", "tool": "file", "description": "Re-write files after debug loop, reset flags"},
        {"name": "node_analyze_impact", "type": "llm", "role": "analyze", "description": "Blast radius analysis using dependency graph"},
        {"name": "node_run_tests", "type": "tool", "tool": "pytest", "description": "Run TDD tests via pytest subprocess"},
        {"name": "node_systematic_debug", "type": "llm", "role": "executor", "description": "Root-cause hypothesis + one fix at a time"},
        {"name": "node_verify", "type": "composite", "description": "Verification gate: lint + tests + LLM spec check"},
        {"name": "node_report", "type": "llm", "role": "summarize", "description": "Generate structured report of what was done"},
        {"name": "node_commit", "type": "tool", "tool": "git", "description": "Commit changes to the git branch"},
        {"name": "node_publish", "type": "tool", "tool": "github", "description": "[v1.3] Push branch + create PR + optional auto-merge"},  # [v1.3]
        {"name": "node_distill_memory", "type": "llm", "role": "planner", "description": "Distill procedural memory for future runs"},
        {"name": "node_create_skill", "type": "tool", "tool": "file", "description": "Generate a new skill file (bypasses TDD, has AST validation)"},
    ],
    "edges": [
        {"from": "node_classify_task", "to": "node_brainstorm", "condition": "route_after_classify: feature/fix/refactor/edit/audit"},
        {"from": "node_classify_task", "to": "node_create_skill", "condition": "route_after_classify: create_skill"},
        {"from": "node_classify_task", "to": "node_validate_input", "condition": "route_after_classify: validate first"},
        {"from": "node_classify_task", "to": "END", "condition": "route_after_classify: unclear"},
        {"from": "node_validate_input", "to": "node_brainstorm"},
        {"from": "node_create_skill", "to": "END", "condition": "create_skill bypass (skips TDD)"},
        {"from": "node_brainstorm", "to": "node_write_plan"},
        {"from": "node_write_plan", "to": "node_git_branch"},
        {"from": "node_git_branch", "to": "node_write_tests"},
        {"from": "node_write_tests", "to": "node_execute_step"},
        {"from": "node_execute_step", "to": "node_write_files"},
        {"from": "node_write_files", "to": "node_analyze_impact", "condition": "route_after_write_files: fix/refactor/improve/feature/audit/edit"},
        {"from": "node_write_files", "to": "node_verify", "condition": "route_after_write_files: other"},
        {"from": "node_analyze_impact", "to": "node_run_tests"},
        {"from": "node_run_tests", "to": "node_verify", "condition": "route_after_run_tests: passed or max_retries"},
        {"from": "node_run_tests", "to": "node_systematic_debug", "condition": "route_after_run_tests: failed"},
        {"from": "node_systematic_debug", "to": "node_write_files", "condition": "debug loop (type: loop)", "type": "loop"},
        {"from": "node_verify", "to": "node_report", "condition": "route_after_verify: verification_passed"},
        {"from": "node_verify", "to": "END", "condition": "route_after_verify: failed"},
        {"from": "node_report", "to": "node_commit"},
        {"from": "node_commit", "to": "node_publish"},  # [v1.3]
        {"from": "node_publish", "to": "node_distill_memory"},  # [v1.3]
        {"from": "node_distill_memory", "to": "END"},
    ],
    "loops": [
        {
            "name": "debug_loop",
            "nodes": ["node_write_files", "node_analyze_impact", "node_run_tests", "node_systematic_debug"],
            "exit_condition": "tdd_status == passed OR tdd_status == max_retries_exceeded",
            "max_iterations": "cfg.autocode_max_retries (default from .env)",
        },
    ],
    "branches": [
        {
            "name": "create_skill",
            "trigger": "task_type == create_skill",
            "path": ["node_classify_task", "node_create_skill", "END"],
            "skips": ["validate", "brainstorm", "plan", "branch", "tests", "execute", "write_files", "analyze_impact", "run_tests", "debug", "verify", "report", "commit", "distill_memory"],
            "note": "Bypasses TDD but has AST syntax validation (v1.0.2 #16) before writing the skill file.",
        },
    ],
    "safety_features": ["protected_files", "git_branch", "atomic_writes", "test_verification", "path_traversal_guard"],
}

# Global compiled graph instance
_COMPILED_GRAPH = None

def build_graph() -> StateGraph:
    """
    Build the LangGraph state machine for the autocode workflow.
    """
    workflow = StateGraph(AutocodeState)

    # Add all nodes
    workflow.add_node("node_classify_task", node_classify_task)
    workflow.add_node("node_validate_input", node_validate_input)
    workflow.add_node("node_brainstorm", node_brainstorm)
    workflow.add_node("node_write_plan", node_write_plan)
    workflow.add_node("node_git_branch", node_git_branch)
    workflow.add_node("node_write_tests", node_write_tests)
    workflow.add_node("node_execute_step", node_execute_step)
    workflow.add_node("node_run_tests", node_run_tests)
    workflow.add_node("node_analyze_impact", node_analyze_impact)
    workflow.add_node("node_systematic_debug", node_systematic_debug)
    workflow.add_node("node_write_files", node_write_files)
    workflow.add_node("node_write_files_with_flag_reset", node_write_files_with_flag_reset)
    workflow.add_node("node_verify", node_verify)
    workflow.add_node("node_commit", node_commit)
    workflow.add_node("node_publish", node_publish)  # [v1.3]
    workflow.add_node("node_distill_memory", node_distill_memory)
    workflow.add_node("node_create_skill", node_create_skill)
    workflow.add_node("node_report", node_report)

    # Set entry point
    workflow.set_entry_point("node_classify_task")

    # Route after classification
    workflow.add_conditional_edges(
        "node_classify_task",
        route_after_classify,
        {
            "node_brainstorm": "node_brainstorm",
            "node_create_skill": "node_create_skill",
            "node_validate_input": "node_validate_input",
            "END": END,
        },
    )

    # Input validation
    workflow.add_edge("node_validate_input", "node_brainstorm")

    # Direct edges for main flow
    workflow.add_edge("node_create_skill", END)
    workflow.add_edge("node_brainstorm", "node_write_plan")
    workflow.add_edge("node_write_plan", "node_git_branch")
    workflow.add_edge("node_git_branch", "node_write_tests")
    workflow.add_edge("node_write_tests", "node_execute_step")
    workflow.add_edge("node_execute_step", "node_write_files")

    # Route after write_files (TDD loop vs verification)
    workflow.add_conditional_edges(
        "node_write_files",
        route_after_write_files,
        {
            "node_analyze_impact": "node_analyze_impact",
            "node_verify": "node_verify",
        },
    )

    # Route after analyze_impact (Always proceeds to run_tests)
    workflow.add_conditional_edges(
        "node_analyze_impact",
        route_after_analyze_impact,
        {
            "node_run_tests": "node_run_tests",
        },
    )

    # Route after run_tests (pass vs debug)
    workflow.add_conditional_edges(
        "node_run_tests",
        route_after_run_tests,
        {
            "node_verify": "node_verify",
            "node_systematic_debug": "node_systematic_debug",
        },
    )

    # Debug loop
    workflow.add_edge("node_systematic_debug", "node_write_files")

    # Route after verification
    workflow.add_conditional_edges(
        "node_verify",
        route_after_verify,
        {
            "report": "node_report",
            "END": END,
        },
    )

    # Report -> commit -> publish -> distill -> END  [v1.3: +publish]
    workflow.add_edge("node_report", "node_commit")
    workflow.add_edge("node_commit", "node_publish")  # [v1.3]
    workflow.add_edge("node_publish", "node_distill_memory")  # [v1.3]
    workflow.add_edge("node_distill_memory", END)

    return workflow

def get_graph():
    """
    Get the singleton compiled graph instance.
    """
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        workflow = build_graph()
        _COMPILED_GRAPH = workflow.compile()
    return _COMPILED_GRAPH


def invoke_with_timeout(initial_state: dict) -> dict:
    """Invoke the autocode graph with the configured AUTOCODE_GRAPH_TIMEOUT.

    [P2 #30] cfg.autocode_graph_timeout was defined but never used.
    Now wraps graph.invoke() with a threading-based timeout to prevent
    hung workflows from blocking forever.
    """
    import threading
    from core.config import cfg

    graph = get_graph()
    result = {"status": "failed", "error": "Graph invocation timed out"}
    timeout = getattr(cfg, "autocode_graph_timeout", 300)

    def _invoke():
        nonlocal result
        result = graph.invoke(initial_state)

    thread = threading.Thread(target=_invoke, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        # Thread is still running — timeout exceeded
        return {
            "status": "failed",
            "error": f"Autocode graph timed out after {timeout}s",
            "trace_id": initial_state.get("trace_id", ""),
        }
    return result