"""Shared fixtures for core/net tests."""
from __future__ import annotations

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_budget_tracker():
    """Reset the global budget tracker singleton before each test."""
    from core.net.budget import _budget_tracker
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()
    _budget_tracker._last_reset_date = __import__("datetime").date.today()
    yield
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()
