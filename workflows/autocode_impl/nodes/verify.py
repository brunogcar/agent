"""[v2.0] Backward-compat wrapper — calls run_pytest + run_lint + llm_review + verify_decision.

The original node_verify was split into 4 nodes in Phase 3.2:
  - node_run_pytest: fresh pytest subprocess
  - node_run_lint: ruff on modified_files
  - node_llm_review: LLM spec check
  - node_verify_decision: compose results + hallucination guard

This wrapper preserves the original API for any external callers that import
node_verify directly. The graph now uses the 4 separate nodes.
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState
from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
from workflows.autocode_impl.nodes.run_lint import node_run_lint
from workflows.autocode_impl.nodes.llm_review import node_llm_review
from workflows.autocode_impl.nodes.verify_decision import node_verify_decision


def node_verify(state: AutocodeState) -> dict:
    """[v2.0] Backward-compat wrapper — runs all 4 split nodes in sequence.

    Merges their partial state updates into one dict (matching the original
    return shape). The graph uses the 4 separate nodes directly; this wrapper
    is for external callers + tests that import node_verify.
    """
    result: dict = {}
    for node_fn in (node_run_pytest, node_run_lint, node_llm_review, node_verify_decision):
        updates = node_fn({**state, **result})  # pass merged state forward
        if updates:
            result.update(updates)
    return result
