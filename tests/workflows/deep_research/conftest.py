"""Shared fixtures for deep_research workflow tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def base_state():
    """Base DeepResearchState for tests.

    Provides sensible defaults for all fields so individual tests only
    override what they need.
    """
    return {
        "goal": "What is LangGraph?",
        "trace_id": "test-trace-001",
        "iteration": 0,
        "consecutive_empty_iterations": 0,
        "budget_api_calls": 5,
        "budget_browser_actions": 2,
        "budget_events": [],
        "max_iterations": 10,
        "completeness_threshold": 85.0,
        "convergence_threshold": 0.85,
        "knowledge_base": "",
        "_prev_knowledge": "",
        "completeness": 0.0,
        "converged": False,
        "sub_queries": [],
        "pending_queries": [],
        "extracted_evidence": [],
        "failed_sources": [],
        "seen_urls": [],
        "memory_context": "",
        "synthesis": "",
    }
