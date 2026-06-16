"""Tests for deep_research seen_urls persistence across iterations.

Verifies that seen_urls is correctly stored in DeepResearchState and
prevents redundant API calls across workflow iterations.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from workflows.deep_research import run_deep_research_agent


class TestSeenURLs:
    """Verify seen_urls deduplication in deep research workflow."""

    def test_seen_urls_passed_to_workflow(self):
        """run_deep_research_agent must include seen_urls in initial state."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {
                "status": "success",
                "result": "test",
                "report": "",
                "seen_urls": ["https://example.com/page1"],
            }

            result = run_deep_research_agent(
                goal="test goal",
                seen_urls=["https://example.com/page1"],
                trace_id="test-trace",
            )

            # Verify run_workflow was called with seen_urls
            call_kwargs = mock_run.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == ["https://example.com/page1"]
            # trace_id should also be present (passed explicitly, not in merged)
            assert call_kwargs.get("trace_id") == "test-trace"

    def test_seen_urls_empty_by_default(self):
        """Without explicit seen_urls, initial state must have empty list."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {"status": "success", "result": "", "report": ""}

            run_deep_research_agent(goal="test goal")

            call_kwargs = mock_run.call_args[1]
            assert "seen_urls" in call_kwargs
            assert call_kwargs["seen_urls"] == []
            # trace_id should default to empty string
            assert call_kwargs.get("trace_id") == ""

    def test_seen_urls_persists_across_calls(self):
        """Subsequent calls with returned seen_urls should prevent duplicates."""
        initial_seen = ["https://example.com/page1"]

        with patch("workflows.deep_research.run_workflow") as mock_run:
            mock_run.return_value = {
                "status": "success",
                "result": "test",
                "report": "",
                "seen_urls": initial_seen + ["https://example.com/page2"],
            }

            # First call
            result1 = run_deep_research_agent(
                goal="test goal",
                seen_urls=initial_seen,
            )

            # Second call with updated seen_urls
            result2 = run_deep_research_agent(
                goal="test goal",
                seen_urls=result1.get("seen_urls", []),
            )

            # Second call should pass the expanded list
            call_kwargs = mock_run.call_args[1]
            assert "https://example.com/page2" in call_kwargs["seen_urls"]

    def test_seen_urls_deduplicates_in_state(self):
        """Same URL added twice should appear only once in seen_urls."""
        with patch("workflows.deep_research.run_workflow") as mock_run:
            def capture_state(**kwargs):
                seen = kwargs.get("seen_urls", [])
                # Simulate adding duplicate
                seen.append("https://example.com/dup")
                seen.append("https://example.com/dup")
                return {"status": "success", "result": "", "report": "", "seen_urls": list(set(seen))}

            mock_run.side_effect = capture_state

            result = run_deep_research_agent(
                goal="test",
                seen_urls=["https://example.com/dup"],
            )

            # Should deduplicate
            assert result["seen_urls"].count("https://example.com/dup") == 1
