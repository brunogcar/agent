"""
workflows/autocode_impl/mermaid.py -- LangGraph → Mermaid flowchart exporter.

Extracts nodes, static edges, and conditional routes from a compiled StateGraph
and formats them as a valid Mermaid TD diagram. Zero external dependencies.

Usage:
    from workflows.autocode_impl.graph import build_graph
    from workflows.autocode_impl.mermaid import export_mermaid

    graph = build_graph()
    print(export_mermaid(graph))
    # Paste output into https://mermaid.live to visualize routing
"""

from __future__ import annotations

from langgraph.graph import StateGraph

def export_mermaid(graph: StateGraph) -> str:
    """Export a LangGraph StateGraph to a Mermaid flowchart string.

    [P1 #5] Uses getattr() with defaults for all LangGraph internal attributes
    to guard against API changes across LangGraph versions.
    """
    lines = ["graph TD"]

    # Nodes — use getattr for LangGraph internal API compatibility
    nodes = getattr(graph, "nodes", {})
    for name in nodes:
        safe = name.replace(" ", "_").replace("-", "_")
        lines.append(f'    {safe}["{name}"]')

    # Static edges
    for src, tgt in getattr(graph, "edges", []):
        s = src.replace(" ", "_").replace("-", "_")
        t = tgt.replace(" ", "_").replace("-", "_")
        lines.append(f"    {s} --> {t}")

    # Conditional edges — use getattr for internal API compatibility
    cond = getattr(graph, "conditional_edges", {})
    for src, routes in cond.items():
        s = src.replace(" ", "_").replace("-", "_")
        if isinstance(routes, dict):
            for route_name, tgt in routes.items():
                t = tgt.replace(" ", "_").replace("-", "_")
                lines.append(f"    {s} -->|{route_name}| {t}")
                
    return "\n".join(lines)