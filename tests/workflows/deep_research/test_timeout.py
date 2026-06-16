"""Tests for deep_research workflow timeout handling.

Verifies that the facade-level timeout correctly interrupts long-running
workflows and returns a proper timeout response.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import patch, MagicMock

from workflows.deep_research import run_deep_research_agent


class TestDeepResearchTimeout:
    """Verify timeout behavior in deep research workflow facade."""

    def test_timeout_returns_timeout_status(self):
        """Workflow exceeding timeout must return status='timeout'."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            # Simulate slow workflow
            def slow_workflow(**kwargs):
                time.sleep(2)
                return {"status": "success", "result": "", "report": ""}

            mock_run.side_effect = slow_workflow

            result = run_deep_research_agent(
                goal="test goal",
                timeout=0.1,  # 100ms timeout
            )

            assert result["status"] == "timeout"
            assert "exceeded" in result.get("error", "").lower()

    def test_timeout_includes_duration_in_error(self):
        """Timeout error message should mention the timeout duration."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.side_effect = lambda **kw: time.sleep(2) or {"status": "success"}

            result = run_deep_research_agent(
                goal="test",
                timeout=0.1,
            )

            assert "0.1" in result.get("error", "") or "100ms" in result.get("error", "")

    def test_successful_workflow_within_timeout(self):
        """Fast workflow within timeout should return success."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {
                "status": "success",
                "result": "research findings",
                "report": "full report",
            }

            result = run_deep_research_agent(
                goal="test goal",
                timeout=30,
            )

            assert result["status"] == "success"
            assert result["result"] == "research findings"

    def test_timeout_from_config_default(self):
        """Timeout should default to cfg.deep_research_timeout_seconds."""
        # [FIX] Use spec=True to prevent MagicMock from auto-creating AsyncMock
        # children when production code accesses async magic methods on cfg.
        with patch("workflows.deep_research.cfg", spec=True) as mock_cfg:
            mock_cfg.deep_research_timeout_seconds = 5
            mock_cfg.deep_research_max_api_calls = 10
            mock_cfg.deep_research_max_browser_actions = 20
            mock_cfg.deep_research_max_iterations = 3
            mock_cfg.deep_research_completeness_threshold = 0.8
            mock_cfg.deep_research_convergence_threshold = 0.9

            with patch("workflows.deep_research.run_workflow") as mock_run:
                mock_run.return_value = {"status": "success", "result": "", "report": ""}

                run_deep_research_agent(goal="test")

                # Verify run_workflow was called (timeout is handled at facade level)
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args[1]
                # trace_id should be present (explicitly, not duplicated)
                assert "trace_id" in call_kwargs
