"""Graph builder and metadata for the understand workflow.

[Decision] This is the v1.0 split — the previous version (async nodes in a
monolithic file) is now Pre-v1.0 in the CHANGELOG. The async→sync conversion
and 16 bug fixes were done in the Pre-v1.0 → v1.0 transition.

[Decision] Uses UnderstandState (not WorkflowState from base.py) because
understand has unique fields: project_path, is_agent_root, project_id,
artifact_dir, files_to_parse, files_parsed, edges_created. These don't
exist in the shared WorkflowState and adding them would bloat it.

[Decision] base.py imports build_understand_graph() and _default_state()
from the thin facade (workflows/understand.py), which re-exports from here.
This is the same pattern as research_impl, autocode_impl, deep_research_impl.
"""
from __future__ import annotations

from pathlib import Path
from langgraph.graph import StateGraph, END
from workflows.understand_impl.state import UnderstandState
from workflows.understand_impl.nodes.init_project import node_init_project
from workflows.understand_impl.nodes.discover_files import node_discover_files
from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
from workflows.understand_impl.nodes.report import node_report


WORKFLOW_METADATA = {
    "name": "understand",
    "version": "1.2",
    "description": "Build codebase knowledge graph: init → discover → parse → report",
    "nodes": [
        {"name": "node_init_project", "description": "Initialize ProjectManager and verify GraphStore"},
        {"name": "node_discover_files", "description": "Scan for changed/new Python files via chunked MD5"},
        {"name": "node_parse_and_store", "description": "Parse imports via AST and store dependency edges"},
        {"name": "node_report", "description": "Generate codebase overview report"},
    ],
    "edges": [
        {"from": "node_init_project", "to": "node_discover_files"},
        {"from": "node_discover_files", "to": "node_parse_and_store"},
        {"from": "node_parse_and_store", "to": "node_report"},
        {"from": "node_report", "to": "END"},
    ],
}


def build_understand_graph():
    """Build and compile the understand LangGraph StateGraph."""
    workflow = StateGraph(UnderstandState)
    workflow.add_node("node_init_project", node_init_project)
    workflow.add_node("node_discover_files", node_discover_files)
    workflow.add_node("node_parse_and_store", node_parse_and_store)
    workflow.add_node("node_report", node_report)
    workflow.set_entry_point("node_init_project")
    workflow.add_edge("node_init_project", "node_discover_files")
    workflow.add_edge("node_discover_files", "node_parse_and_store")
    workflow.add_edge("node_parse_and_store", "node_report")
    workflow.add_edge("node_report", END)
    return workflow.compile()
