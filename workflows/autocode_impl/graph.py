"""
State machine construction for autocode workflow.
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
from workflows.autocode_impl.nodes.memory import node_distill_memory
from workflows.autocode_impl.nodes.create_skill import node_create_skill
from workflows.autocode_impl.nodes.report import node_report
from workflows.autocode_impl.routes import (
    route_after_classify,
    route_after_brainstorm,
    route_after_run_tests,
    route_after_debug,
    route_after_write_files,
    route_after_verify,
    route_after_analyze_impact,
)

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

    # Report -> commit -> distill -> END
    workflow.add_edge("node_report", "node_commit")
    workflow.add_edge("node_commit", "node_distill_memory")
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