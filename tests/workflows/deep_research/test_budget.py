"""Tests for budget tracking utilities."""
from __future__ import annotations

from workflows.deep_research_core.budget import (
    decrement_api_calls,
    decrement_browser_actions,
    log_event,
    is_api_budget_exhausted,
    is_browser_budget_exhausted,
    format_audit,
)


def test_decrement_api_calls():
    assert decrement_api_calls({"budget_api_calls": 5}) == {"budget_api_calls": 4}


def test_decrement_api_calls_floor():
    assert decrement_api_calls({"budget_api_calls": 0}) == {"budget_api_calls": 0}


def test_decrement_browser_actions():
    assert decrement_browser_actions({"budget_browser_actions": 3}) == {"budget_browser_actions": 2}


def test_log_event():
    result = log_event({"iteration": 2, "budget_events": []}, "tavily", "search", "query")
    assert len(result["budget_events"]) == 1
    assert result["budget_events"][0]["tool"] == "tavily"


def test_is_api_budget_exhausted():
    assert is_api_budget_exhausted({"budget_api_calls": 0}) is True
    assert is_api_budget_exhausted({"budget_api_calls": 1}) is False


def test_is_browser_budget_exhausted():
    assert is_browser_budget_exhausted({"budget_browser_actions": 0}) is True
    assert is_browser_budget_exhausted({"budget_browser_actions": 5}) is False


def test_format_audit():
    events = [{"iteration": 1, "tool": "tavily", "action": "search", "reason": "q"}]
    text = format_audit(events)
    assert "tavily" in text
    assert "search" in text
