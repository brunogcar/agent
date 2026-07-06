"""Shared fixtures for data workflow tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def base_state():
    """Base WorkflowState for data tests."""
    return {
        "workflow": "data",
        "goal": "Compute sum of list",
        "trace_id": "t1",
        "status": "running",
        "error": "",
        "result": "",
        "artifacts": [],
        "retries": 0,
        "code": "",
        "memory_context": "",
        "output": "",
        "exec_error": "",
    }
