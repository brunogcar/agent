"""Tests for research workflow parallel scrape node.

Verifies nested parallel guard rejection and worker timeout handling.
"""
from __future__ import annotations

import json
import time
import pytest
from unittest.mock import patch, MagicMock

from workflows.research import node_parallel_scrape, _is_nested_parallel


class TestNestedParallelGuard:
    """Verify _is_nested_parallel() prevents deadlock."""

    def test_nested_parallel_rejected(self):
        """When _is_nested_parallel returns True, node must reject immediately."""
        state = {
            "goal": "test",
            "trace_id": "test-trace",
            "search_results": json.dumps([{"url": "https://example.com", "title": "Test"}]),
        }

        with patch("workflows.research._is_nested_parallel", return_value=True):
            result = node_parallel_scrape(state)

        assert result["search_results"] == ""
        # Should have logged the rejection

    def test_not_nested_proceeds(self):
        """When not nested, node should process URLs normally."""
        state = {
            "goal": "test",
            "trace_id": "test-trace",
            "search_results": json.dumps([{"url": "https://example.com", "title": "Test"}]),
        }

        with patch("workflows.research._is_nested_parallel", return_value=False), \
             patch("workflows.research.ThreadPoolExecutor") as mock_pool, \
             patch("workflows.research._scrape_and_summarize") as mock_scrape:

            mock_future = MagicMock()
            mock_future.result.return_value = {
                "url": "https://example.com",
                "title": "Test",
                "status": "success",
                "summary": "Summary text",
            }
            mock_pool.return_value.__enter__.return_value.submit.return_value = mock_future
            mock_pool.return_value.__enter__.return_value.max_workers = 2

            # Mock as_completed to yield our future
            with patch("workflows.research.as_completed", return_value=[mock_future]):
                result = node_parallel_scrape(state)

        # Should have attempted processing
        assert result is not None


class TestWorkerTimeout:
    """Verify 30-second timeout on worker execution."""

    def test_worker_exceeds_timeout(self):
        """Worker taking longer than timeout should be killed."""
        state = {
            "goal": "test",
            "trace_id": "test-trace",
            "search_results": json.dumps([{"url": "https://example.com", "title": "Test"}]),
        }

        # [FIX] Use spec=True to prevent MagicMock from auto-creating AsyncMock
        # children when production code accesses async magic methods on cfg.
        with patch("core.config.cfg", spec=True) as mock_cfg:
            mock_cfg.worker_timeout = 0.1  # 100ms for fast test
            mock_cfg.max_concurrent_workers = 2
            mock_cfg.web_max_text_chars = 8000
            mock_cfg.research_browser_fallback_max = 0

            with patch("workflows.research._is_nested_parallel", return_value=False), \
                 patch("workflows.research.ThreadPoolExecutor") as mock_pool:

                mock_future = MagicMock()
                # Simulate timeout
                from concurrent.futures import TimeoutError
                mock_future.result.side_effect = TimeoutError("Worker timed out")

                mock_pool.return_value.__enter__.return_value.submit.return_value = mock_future

                with patch("workflows.research.as_completed", return_value=[mock_future]):
                    result = node_parallel_scrape(state)

                # Should handle timeout gracefully
                assert result is not None

    def test_global_timeout_on_as_completed(self):
        """as_completed timeout should be worker_timeout + 30."""
        state = {
            "goal": "test",
            "trace_id": "test-trace",
            "search_results": json.dumps([{"url": "https://example.com", "title": "Test"}]),
        }

        # [FIX] Use spec=True to prevent MagicMock from auto-creating AsyncMock
        # children when production code accesses async magic methods on cfg.
        with patch("core.config.cfg", spec=True) as mock_cfg:
            mock_cfg.worker_timeout = 10
            mock_cfg.max_concurrent_workers = 2
            mock_cfg.web_max_text_chars = 8000
            mock_cfg.research_browser_fallback_max = 0

            # Verify the timeout value passed to as_completed
            with patch("workflows.research._is_nested_parallel", return_value=False), \
                 patch("workflows.research.ThreadPoolExecutor") as mock_pool, \
                 patch("workflows.research.as_completed") as mock_as_completed:

                mock_future = MagicMock()
                mock_future.result.return_value = {
                    "url": "https://example.com",
                    "title": "Test",
                    "status": "success",
                    "summary": "Summary",
                }
                mock_pool.return_value.__enter__.return_value.submit.return_value = mock_future
                mock_as_completed.return_value = [mock_future]

                node_parallel_scrape(state)

                # as_completed should be called with timeout=worker_timeout + 30
                call_args = mock_as_completed.call_args
                assert call_args[1]["timeout"] == 40  # 10 + 30
