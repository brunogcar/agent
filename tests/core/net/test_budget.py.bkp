"""tests/core/test_budget.py — API cost tracking and budget enforcement tests.

v1.2: Added for core.net.budget module.
"""
from __future__ import annotations

import pytest

from core.net.budget import (
    APICostTracker,
    BudgetConfig,
    record_tool_call,
    check_budget,
    get_budget_status,
    set_tool_budget,
)


class TestAPICostTracker:
    """Test cost tracking and budget enforcement."""

    def setup_method(self):
        """Reset tracker state before each test."""
        tracker = APICostTracker()
        # Reset internal state
        tracker._calls.clear()
        tracker._configs.clear()

    def test_record_call_increments(self):
        tracker = APICostTracker()
        tracker.record_call("tavily.search")
        tracker.record_call("tavily.search")
        assert tracker._calls["tavily.search"] == 2

    def test_can_afford_with_no_limit(self):
        tracker = APICostTracker()
        assert tracker.can_afford("tavily.search") is True

    def test_can_afford_within_limit(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=5))
        tracker.record_call("tavily.search", cost=3)
        assert tracker.can_afford("tavily.search") is True

    def test_can_afford_at_limit(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=5))
        tracker.record_call("tavily.search", cost=5)
        assert tracker.can_afford("tavily.search") is False

    def test_can_afford_over_limit(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=5))
        tracker.record_call("tavily.search", cost=6)
        assert tracker.can_afford("tavily.search") is False

    def test_warning_threshold(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10, warning_threshold=0.8))
        tracker.record_call("tavily.search", cost=8)
        assert tracker.is_warning("tavily.search") is True

    def test_no_warning_below_threshold(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10, warning_threshold=0.8))
        tracker.record_call("tavily.search", cost=7)
        assert tracker.is_warning("tavily.search") is False

    def test_get_status_single_tool(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=100))
        tracker.record_call("tavily.search", cost=25)
        status = tracker.get_status("tavily.search")
        assert status["tavily.search"]["used"] == 25
        assert status["tavily.search"]["limit"] == 100
        assert status["tavily.search"]["remaining"] == 75

    def test_get_status_all_tools(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=100))
        tracker.set_budget("tavily.extract", BudgetConfig(daily_limit=50))
        tracker.record_call("tavily.search", cost=10)
        tracker.record_call("tavily.extract", cost=5)
        status = tracker.get_status()
        assert "tavily.search" in status
        assert "tavily.extract" in status

    def test_thread_safety(self):
        """Concurrent record_call operations should not lose counts."""
        import threading
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10000))

        def worker():
            for _ in range(100):
                tracker.record_call("tavily.search")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker._calls["tavily.search"] == 1000


class TestBudgetHelpers:
    """Test module-level helper functions."""

    def test_record_tool_call(self):
        record_tool_call("tavily.search")
        status = get_budget_status("tavily.search")
        assert status["tavily.search"]["used"] >= 1

    def test_check_budget_default(self):
        assert check_budget("any_tool") is True

    def test_set_tool_budget(self):
        set_tool_budget("tavily.search", daily_limit=50)
        assert check_budget("tavily.search") is True
        # Record enough calls to exhaust budget
        for _ in range(50):
            record_tool_call("tavily.search")
        assert check_budget("tavily.search") is False
