"""[v2.0] Backward-compat wrapper — calls push + create_pr + merge_pr.

The original node_publish was split into 3 nodes in Phase 3.3:
  - node_push: push branch to remote
  - node_create_pr: create pull request
  - node_merge_pr: auto-merge PR (if enabled)

This wrapper preserves the original API for any external callers that import
node_publish directly. The graph now uses the 3 separate nodes.
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.nodes.push import node_push
from workflows.autocode_impl.nodes.create_pr import node_create_pr
from workflows.autocode_impl.nodes.merge_pr import node_merge_pr


def node_publish(state: AutocodeState) -> dict:
    """[v2.0] Backward-compat wrapper — runs all 3 split nodes in sequence.

    Merges their partial state updates into one dict (matching the original
    return shape). The graph uses the 3 separate nodes directly; this wrapper
    is for external callers + tests that import node_publish.
    """
    result: dict = {}
    for node_fn in (node_push, node_create_pr, node_merge_pr):
        updates = node_fn({**state, **result})  # pass merged state forward
        if updates:
            result.update(updates)
    return result
