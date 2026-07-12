"""workflows/autoresearch.py — Thin facade for the autoresearch workflow.

Autonomous experiment-driven optimization: modify → run → measure → keep/discard → repeat.
Inspired by karpathy/autoresearch.

[v1.0] Initial implementation. The facade re-exports the graph builder and
WORKFLOW_METADATA from the autoresearch_impl subpackage, matching the pattern
used by research / autocode / deep_research / understand / data.
"""
from __future__ import annotations

from workflows.autoresearch_impl.graph import build_autoresearch_graph, WORKFLOW_METADATA

__all__ = ["build_autoresearch_graph", "WORKFLOW_METADATA"]
