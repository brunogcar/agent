"""[v2.0] Backward-compat wrapper — calls apply_patches + write_new_files + persist_artifacts.

The original node_write_files was split into 3 nodes in Phase 3.1:
  - node_apply_patches: str_replace patches
  - node_write_new_files: new file writes + files_map
  - node_persist_artifacts: test file + generated code + debug log

This wrapper preserves the original API for any external callers that import
node_write_files directly. The graph now uses the 3 separate nodes.
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.nodes.apply_patches import node_apply_patches, _is_path_safe  # re-export
from workflows.autocode_impl.nodes.write_new_files import node_write_new_files
from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts


def node_write_files(state: AutocodeState) -> dict:
    """[v2.0] Backward-compat wrapper — runs all 3 split nodes in sequence.

    Merges their partial state updates into one dict (matching the original
    return shape). The graph uses the 3 separate nodes directly; this wrapper
    is for external callers + tests that import node_write_files.
    """
    result: dict = {}
    for node_fn in (node_apply_patches, node_write_new_files, node_persist_artifacts):
        updates = node_fn({**state, **result})  # pass merged state forward
        if updates:
            result.update(updates)
    return result
