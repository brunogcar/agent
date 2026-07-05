"""workflows/research.py — Thin facade for the research workflow.

v1.0: Split from monolithic file into research_impl/ subpackage.
All node logic lives in workflows/research_impl/nodes/.
Graph builder and metadata in workflows/research_impl/graph.py.
"""
from __future__ import annotations

# Re-export the graph builder for backward compatibility.
# base.py imports build_research_graph from here.
from workflows.research_impl.graph import build_research_graph, WORKFLOW_METADATA

__all__ = ["build_research_graph", "WORKFLOW_METADATA"]
