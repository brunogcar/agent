"""Tests for v3.6 #35 cancellation-aware subprocess calls."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestRemainingTimeout:
    """Test _remaining_timeout helper."""

    def test_returns_default_when_no_start_time(self):
        from workflows.autocode_impl.helpers import _remaining_timeout
        # _graph_start_time is 0.0 in tests (not set)
        assert _remaining_timeout(30) == 30

    def test_caps_at_remaining_time(self):
        from workflows.autocode_impl.helpers import _remaining_timeout, _graph_start_time
        import time as _time
        with patch("workflows.autocode_impl.helpers._graph_start_time", _time.time() - 290):
            with patch("core.config.cfg") as mock_cfg:
                mock_cfg.autocode_graph_timeout = 300
                result = _remaining_timeout(30)
                # 290s elapsed, 10s remaining → min(30, 10) = 10
                assert result <= 11  # allow 1s slack

    def test_returns_1_when_expired(self):
        from workflows.autocode_impl.helpers import _remaining_timeout
        import time as _time
        with patch("workflows.autocode_impl.helpers._graph_start_time", _time.time() - 500):
            with patch("core.config.cfg") as mock_cfg:
                mock_cfg.autocode_graph_timeout = 300
                assert _remaining_timeout(30) == 1


class TestCancellationChecks:
    """Test that nodes check cancellation before/after subprocess."""

    def test_run_pytest_checks_cancellation_before(self, base_state):
        """run_pytest should return 'Cancelled' if cancellation is requested before the subprocess."""
        from workflows.autocode_impl.nodes.run_pytest import node_run_pytest
        with patch("workflows.autocode_impl.nodes.run_pytest.is_cancellation_requested", return_value=True):
            result = node_run_pytest(base_state)
        assert result.get("tests_passed") is False
        assert "Cancelled" in result.get("_pytest_output", "")

    def test_run_lint_checks_cancellation_before(self, base_state):
        """run_lint should return 'Cancelled' if cancellation is requested."""
        from workflows.autocode_impl.nodes.run_lint import node_run_lint
        base_state["files_state"] = {"modified_files": ["test.py"]}
        with patch("workflows.autocode_impl.nodes.run_lint.is_cancellation_requested", return_value=True):
            result = node_run_lint(base_state)
        assert "Cancelled" in result.get("lint_output", "")

    def test_run_tests_checks_cancellation_before(self, base_state):
        """run_tests should return 'Cancelled' if cancellation is requested."""
        from workflows.autocode_impl.nodes.run_tests import node_run_tests
        base_state["tdd"]["status"] = ""
        base_state["test_files"] = ["test_foo.py"]
        with patch("workflows.autocode_impl.nodes.run_tests.is_cancellation_requested", return_value=True):
            result = node_run_tests(base_state)
        assert result.get("success") is False
        assert "Cancelled" in result.get("stderr", "")
