"""
workflows/autocode_helpers/mermaid.py -- LangGraph → Mermaid flowchart exporter.

Extracts nodes, static edges, and conditional routes from a compiled StateGraph
and formats them as a valid Mermaid TD diagram. Zero external dependencies.

Usage:
    from workflows.autocode_helpers.graph import build_graph
    from workflows.autocode_helpers.mermaid import export_mermaid

    graph = build_graph()
    print(export_mermaid(graph))
    # Paste output into https://mermaid.live to visualize routing
"""

from __future__ import annotations

from langgraph.graph import StateGraph

def export_mermaid(graph: StateGraph) -> str:
    """Export a LangGraph StateGraph to a Mermaid flowchart string."""
    lines = ["graph TD"]
    
    # Nodes
    for name in graph.nodes:
        safe = name.replace(" ", "_").replace("-", "_")
        lines.append(f'    {safe}["{name}"]')
        
    # Static edges
    for src, tgt in getattr(graph, "edges", []):
        s = src.replace(" ", "_").replace("-", "_")
        t = tgt.replace(" ", "_").replace("-", "_")
        lines.append(f"    {s} --> {t}")
        
    # Conditional edges
    cond = getattr(graph, "conditional_edges", {})
    for src, routes in cond.items():
        s = src.replace(" ", "_").replace("-", "_")
        if isinstance(routes, dict):
            for route_name, tgt in routes.items():
                t = tgt.replace(" ", "_").replace("-", "_")
                lines.append(f"    {s} -->|{route_name}| {t}")
                
    return "\n".join(lines)