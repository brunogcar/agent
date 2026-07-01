"""Tests for core/net/budget.py — API cost tracking and budget enforcement.

v1.3: Fixed singleton pollution by resetting global tracker in setup_method.
      Added daily reset test.
"""
from __future__ import annotations

import threading

import pytest

from core.net.budget import (
    APICostTracker,
    BudgetConfig,
    record_tool_call,
    check_budget,
    get_budget_status,
    set_tool_budget,
    _budget_tracker,
)


class TestAPICostTracker:
    """Tests for the APICostTracker class (isolated instances)."""

    def test_record_call_increments(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=100))
        tracker.record_call("tavily.search")
        assert tracker._calls["tavily.search"] == 1

    def test_can_afford_at_limit(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=2))
        tracker.record_call("tavily.search")
        tracker.record_call("tavily.search")
        assert tracker.can_afford("tavily.search") is False

    def test_can_afford_unlimited(self):
        tracker = APICostTracker()
        assert tracker.can_afford("tavily.search") is True

    def test_is_warning(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10, warning_threshold=0.8))
        tracker.record_call("tavily.search", cost=8)
        assert tracker._is_warning_unlocked("tavily.search") is True

    def test_is_warning_below_threshold(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10, warning_threshold=0.8))
        tracker.record_call("tavily.search", cost=7)
        assert tracker._is_warning_unlocked("tavily.search") is False

    def test_get_status_single_tool(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10))
        tracker.record_call("tavily.search", cost=5)
        status = tracker.get_status("tavily.search")
        assert status["tavily.search"]["used"] == 5
        assert status["tavily.search"]["limit"] == 10
        assert status["tavily.search"]["remaining"] == 5
        assert "warning" in status["tavily.search"]
        assert "blocked" in status["tavily.search"]

    def test_get_status_all_tools(self):
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10))
        tracker.record_call("tavily.search", cost=3)
        status = tracker.get_status()
        assert "tavily.search" in status
        assert status["tavily.search"]["used"] == 3
        assert "warning" in status["tavily.search"]
        assert "blocked" in status["tavily.search"]

    def test_thread_safety(self):
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

    def test_daily_reset(self):
        """v1.3: Counts reset when date changes."""
        tracker = APICostTracker()
        tracker.set_budget("tavily.search", BudgetConfig(daily_limit=10))
        tracker.record_call("tavily.search", cost=5)
        assert tracker._calls["tavily.search"] == 5

        # Simulate date change
        import datetime
        tracker._last_reset_date = datetime.date.today() - datetime.timedelta(days=1)
        tracker._maybe_reset_daily()
        # v1.3 FIX: After reset, the key is removed from _calls (dict cleared)
        assert tracker._calls.get("tavily.search", 0) == 0
        # Budget should be available again
        assert tracker.can_afford("tavily.search") is True


class TestBudgetHelpers:
    """Tests for module-level singleton helpers.

    v1.3 FIX: setup_method resets the global singleton to prevent test pollution.
    """

    def setup_method(self):
        """Reset global singleton before each test."""
        _budget_tracker._calls.clear()
        _budget_tracker._configs.clear()
        _budget_tracker._last_reset_date = __import__("datetime").date.today()

    def test_record_tool_call(self):
        record_tool_call("tavily.search")
        status = get_budget_status("tavily.search")
        # v1.3 FIX: get_status now returns info even without explicit budget config
        assert status["tavily.search"]["used"] >= 1

    def test_check_budget_default(self):
        assert check_budget("tavily.search") is True

    def test_set_tool_budget(self):
        set_tool_budget("tavily.search", daily_limit=50)
        for _ in range(50):
            record_tool_call("tavily.search")
        assert check_budget("tavily.search") is False

    def test_get_budget_status(self):
        set_tool_budget("tavily.search", daily_limit=100)
        record_tool_call("tavily.search")
        status = get_budget_status("tavily.search")
        assert status["tavily.search"]["used"] == 1
        assert status["tavily.search"]["limit"] == 100
