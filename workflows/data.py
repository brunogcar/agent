"""workflows/data.py — Thin facade for the data workflow.

v1.0: Split from monolithic file into the data_impl/ subpackage with
per-node modules, mirroring research_impl / understand_impl. All node logic
lives in workflows/data_impl/nodes/. Graph builder and metadata live in
workflows/data_impl/graph.py.

base.py imports build_data_graph() from here, which re-exports from
data_impl.graph — same pattern as research.
"""
from __future__ import annotations

from workflows.data_impl.graph import build_data_graph, WORKFLOW_METADATA

__all__ = ["build_data_graph", "WORKFLOW_METADATA"]
