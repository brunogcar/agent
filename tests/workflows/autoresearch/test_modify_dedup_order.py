"""tests/workflows/autoresearch/test_modify_dedup_order.py

[v1.11 A6] Tests that the single-path empty-content check runs BEFORE the
dedup hash check. Pre-v1.11, the order was reversed — two LLM-call failures
(both new_content="") hashed to the same md5("") constant, so the second
failure hit the dedup check first and was misreported as "duplicate
experiment" instead of "proposal new_content is empty". The parallel path
already had the correct order; this file tests the single-path fix.

Coverage:
  TestModifyEmptyCheckOrder — single path: empty content reports "empty"
                              (not "duplicate"); second empty also reports
                              "empty" (not "duplicate of first")
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


class TestModifyEmptyCheckOrder:
    """[v1.11 A6] Single-path empty-content check must run BEFORE dedup hash.

    Pre-v1.11, two empty-content proposals would both hash to md5("") and
    the second would be misreported as "duplicate" instead of "empty".
    """

    def test_empty_content_reports_empty_not_duplicate(self, ar_state):
        """A single empty-content proposal must report 'empty new_content',
        NOT 'duplicate experiment'. Pre-v1.11, the hash was computed first
        (md5("") = d41d8cd9...) and the dedup loop checked it against
        history — if history had a prior empty entry, the error said
        'duplicate'."""
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state["parallel_count"] = 1
        state["experiment_history"] = []  # no prior experiments
        state["current_experiment"] = {
            "iteration": 1,
            "description": "LLM returned empty",
            "new_content": "",  # empty — LLM parse failure
        }
        result = node_modify(state)
        assert result["status"] == "failed"
        assert "empty" in result["error"].lower()
        assert "duplicate" not in result["error"].lower()

    def test_second_empty_reports_empty_not_duplicate(self, ar_state):
        """Two consecutive empty-content proposals: both must report 'empty'.
        Pre-v1.11, the second would hit the dedup check first (md5("") matched
        the first empty's hash stored in experiment_history) and report
        'duplicate experiment — same content as iteration 1' instead of the
        true cause: the LLM returned empty content again."""
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state["parallel_count"] = 1
        # Simulate a prior empty-content experiment in history — its
        # content_hash is md5("") = d41d8cd98f00b204e9800998ecf8427e.
        state["experiment_history"] = [
            {
                "iteration": 1,
                "description": "first LLM failure",
                "metric": 0.0,
                "status": "discard",
                "commit": "",
                "content_hash": "d41d8cd98f00b204e9800998ecf8427e",
            }
        ]
        state["current_experiment"] = {
            "iteration": 2,
            "description": "second LLM failure",
            "new_content": "",  # empty again
        }
        result = node_modify(state)
        assert result["status"] == "failed"
        # Must report "empty" (the true cause), NOT "duplicate".
        assert "empty" in result["error"].lower()
        assert "duplicate" not in result["error"].lower()
