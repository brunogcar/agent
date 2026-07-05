"""Shared fixtures for research workflow tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def base_state():
    """Base WorkflowState for research tests."""
    return {
        "workflow": "research",
        "goal": "test",
        "trace_id": "t1",
        "status": "running",
        "error": "",
        "result": "",
        "artifacts": [],
        "retries": 0,
        "search_results": "",
        "memory_context": "",
    }
