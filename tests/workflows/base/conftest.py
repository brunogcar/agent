"""Shared fixtures for base workflow tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def base_state():
    """Base WorkflowState for tests."""
    return {
        "workflow": "test",
        "goal": "test goal",
        "trace_id": "t1",
        "status": "running",
        "error": "",
        "result": "",
        "artifacts": [],
        "retries": 0,
    }
