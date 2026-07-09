"""Shared fixtures for swarm tool tests.

All swarm infrastructure is fully mocked — no real API calls to any provider.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_providers():
    """Mock 3 cloud providers in llm._registry._providers.

    Returns a dict of {name: mock_provider} for assertion.
    """
    providers = {}

    for name, model in [("openai", "gpt-4o-mini"), ("deepseek", "deepseek-chat"), ("claude", "claude-3-5-haiku-20241022")]:
        mock_provider = MagicMock()
        mock_response = {
            "choices": [{"message": {"content": f"Response from {name}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_provider.chat_completion.return_value = mock_response
        mock_provider.is_available.return_value = True
        providers[name] = mock_provider

    return providers


@pytest.fixture
def mock_llm_registry(mock_providers):
    """Patch llm._registry._providers with mock providers + mock os.getenv for BASE_MODEL.

    Also patches llm.complete (used by consensus synthesis) to return a mock response.
    """
    import os

    # Patch the llm singleton's registry
    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),  # should be skipped by swarm
            **mock_providers,
        }
        # Mock llm.complete for consensus synthesis
        mock_synthesis = MagicMock()
        mock_synthesis.ok = True
        mock_synthesis.text = "Synthesized answer combining all responses."
        mock_llm.complete.return_value = mock_synthesis

        # Patch os.getenv to return model names for each provider
        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "OPENAI_BASE_MODEL":
                return "gpt-4o-mini"
            elif key == "DEEPSEEK_BASE_MODEL":
                return "deepseek-chat"
            elif key == "CLAUDE_BASE_MODEL":
                return "claude-3-5-haiku-20241022"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm


@pytest.fixture
def mock_llm_empty_registry():
    """Patch llm with NO cloud providers (only lmstudio).

    Used to test 'no providers configured' error paths.
    """
    import os

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),  # only local — should be skipped
        }

        with patch("os.getenv", return_value=""):
            yield mock_llm


@pytest.fixture
def mock_failing_providers():
    """Mock providers that all raise exceptions.

    Used to test 'all providers failed' error paths.
    """
    import os

    providers = {}
    for name, model in [("openai", "gpt-4o-mini"), ("deepseek", "deepseek-chat")]:
        mock_provider = MagicMock()
        mock_provider.chat_completion.side_effect = RuntimeError(f"{name} API error")
        mock_provider.is_available.return_value = True
        providers[name] = mock_provider

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),
            **providers,
        }

        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "OPENAI_BASE_MODEL":
                return "gpt-4o-mini"
            elif key == "DEEPSEEK_BASE_MODEL":
                return "deepseek-chat"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm
