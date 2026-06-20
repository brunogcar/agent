"""Shared fixtures for agent tool tests.

All LLM calls are fully mocked; no real LLM requests are made.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_cfg():
    """Mock cfg to prevent AsyncMock leakage from other tests.

    Per test isolation rule: autouse fixture in every test file that imports cfg.
    cfg must be patched where it is imported at module level.
    """
    with patch("tools.agent_core.context.cfg") as mock_cfg_ctx:
        mock_cfg_ctx.max_context_tokens = 8000
        yield mock_cfg_ctx


@pytest.fixture
def mock_llm_result():
    """Return a pre-built MagicMock for a successful llm.complete() result.

    Shape matches LLMResponse.usage: {"prompt": int, "completion": int, "total": int}
    """
    result = MagicMock()
    result.ok = True
    result.text = "mocked response"
    result.model = "test-model"
    result.elapsed = 1.0
    result.usage = {"prompt": 10, "completion": 5, "total": 15}
    result.parsed = None
    result.finish_reason = "stop"
    return result
