"""tests/benchmark/conftest.py — Shared fixtures for benchmark tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_task():
    """A minimal task dict for testing."""
    return {
        "name": "test_task",
        "prompt": "Test prompt",
        "system": "Test system",
        "validator": "exact_match",
        "expected": "test",
        "difficulty": "easy",
        "timeout": 10,
        "max_tokens": 100,
    }
