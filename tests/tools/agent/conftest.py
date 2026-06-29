"""Shared fixtures for agent tool tests."""
from __future__ import annotations

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def clear_agent_state():
    """Clear cache and metrics between every test."""
    from tools.agent_ops.cache import _clear_cache
    from tools.agent_ops.metrics import _clear_metrics
    from tools.agent_ops.parse_warnings import _clear_parse_warnings
    _clear_cache()
    _clear_metrics()
    _clear_parse_warnings()


@pytest.fixture
def mock_cfg():
    """Patch context.cfg with a minimal config object."""
    class FakeCfg:
        model = "test-model"
        temperature = 0.0
        max_tokens = 1000
        timeout = 30
        max_context_tokens = 8000
    with patch("tools.agent_ops.context.cfg", FakeCfg()):
        yield FakeCfg()


@pytest.fixture
def mock_llm_result():
    """Return a fake LLM result. parsed=None so JSON tests parse from text."""
    class FakeResult:
        ok = True
        text = "bug"
        model = "test-model"
        usage = {"total": 10}
        parsed = None  # Tests that need parsed set will override
        error = None
    return FakeResult()
