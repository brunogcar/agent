"""tests/workflows/deep_research/test_budget.py
Tests for budget tracking utilities.

v1.1.1: Removed TestFormatAudit + format_audit import (dead code removed from budget.py).
"""
from __future__ import annotations

from workflows.deep_research_impl.budget import (
    decrement_api_calls,
    decrement_browser_actions,
    log_event,
    is_api_budget_exhausted,
    is_browser_budget_exhausted,
)


class TestDecrementApiCalls:
    def test_decrements(self):
        assert decrement_api_calls({"budget_api_calls": 5}) == {"budget_api_calls": 4}

    def test_floors_at_zero(self):
        assert decrement_api_calls({"budget_api_calls": 0}) == {"budget_api_calls": 0}


class TestDecrementBrowserActions:
    def test_decrements(self):
        assert decrement_browser_actions({"budget_browser_actions": 3}) == {"budget_browser_actions": 2}


class TestLogEvent:
    def test_appends_event(self):
        result = log_event({"iteration": 2, "budget_events": []}, "tavily", "search", "query")
        assert len(result["budget_events"]) == 1
        assert result["budget_events"][0]["tool"] == "tavily"


class TestBudgetExhausted:
    def test_api_exhausted(self):
        assert is_api_budget_exhausted({"budget_api_calls": 0}) is True
        assert is_api_budget_exhausted({"budget_api_calls": 1}) is False

    def test_browser_exhausted(self):
        assert is_browser_budget_exhausted({"budget_browser_actions": 0}) is True
        assert is_browser_budget_exhausted({"budget_browser_actions": 5}) is False
