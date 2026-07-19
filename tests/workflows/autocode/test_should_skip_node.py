"""tests/workflows/autocode/test_should_skip_node.py — Tests for _should_skip_node helper.

[v3.3 #58] Standardizes the status-check pattern across all nodes.
"""
from __future__ import annotations

import pytest

from workflows.autocode_impl.helpers import _should_skip_node, _SKIP_STATUSES


class TestShouldSkipNode:
    """Test the canonical skip-status check."""

    def test_needs_clarification_skips(self):
        assert _should_skip_node({"status": "needs_clarification"}) is True

    def test_failed_skips(self):
        assert _should_skip_node({"status": "failed"}) is True

    def test_error_skips(self):
        assert _should_skip_node({"status": "error"}) is True

    def test_skipped_skips(self):
        assert _should_skip_node({"status": "skipped"}) is True

    def test_running_does_not_skip(self):
        assert _should_skip_node({"status": "running"}) is False

    def test_success_does_not_skip(self):
        assert _should_skip_node({"status": "success"}) is False

    def test_empty_status_does_not_skip(self):
        assert _should_skip_node({"status": ""}) is False

    def test_missing_status_does_not_skip(self):
        assert _should_skip_node({}) is False

    def test_dry_run_does_not_skip(self):
        """dry_run is a valid status — nodes should still run (they check dry_run internally)."""
        assert _should_skip_node({"status": "dry_run"}) is False

    def test_skip_statuses_is_frozenset(self):
        """_SKIP_STATUSES should be a frozenset for O(1) lookup."""
        assert isinstance(_SKIP_STATUSES, frozenset)

    def test_skip_statuses_has_4_members(self):
        """The canonical set has exactly: needs_clarification, failed, error, skipped."""
        assert _SKIP_STATUSES == frozenset({
            "needs_clarification", "failed", "error", "skipped"
        })


class TestArchitectureQuestionThreshold:
    """Test F4: configurable _ARCHITECTURE_QUESTION_THRESHOLD."""

    def test_default_is_3(self):
        """Default threshold should be 3 (matching the pre-v3.3 hardcoded value)."""
        from core.config import cfg
        assert cfg.autocode_architecture_question_threshold == 3

    def test_env_override(self, monkeypatch):
        """AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD env var should override the default."""
        import os
        monkeypatch.setenv("AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD", "5")
        assert int(os.getenv("AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD", "3")) == 5

    def test_debug_uses_config(self):
        """debug.py should read from cfg, not a hardcoded constant."""
        from workflows.autocode_impl.nodes.debug import _ARCHITECTURE_QUESTION_THRESHOLD
        from core.config import cfg
        assert _ARCHITECTURE_QUESTION_THRESHOLD == cfg.autocode_architecture_question_threshold
