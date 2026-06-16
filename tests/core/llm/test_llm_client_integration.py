"""Integration tests for LLMClient complete() and role fallback."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from core.llm_backend.client import LLMClient


@pytest.fixture
def mock_config():
    """Mock configuration for LLM client."""
    with patch("core.llm_backend.config.cfg") as mock_cfg:
        mock_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        mock_cfg.executor_model = "test-model"
        mock_cfg.vision_model = "test-vision-model"
        mock_cfg.model_registry = {
            "executor": {"model": "test-model", "timeout": 120, "provider": "lmstudio"},
            "planner": {"model": "test-model", "timeout": 90, "provider": "lmstudio"},
            "router": {"model": "test-model", "timeout": 15, "provider": "lmstudio"},
            "consultor": {"model": "test-model", "timeout": 60, "provider": "openai"},
        }
        mock_cfg.max_context_tokens = 8000
        yield mock_cfg


@pytest.fixture
def llm_client(mock_config):
    """Create an LLM client with mocked config."""
    return LLMClient()


@pytest.fixture
def mock_provider():
    """Create a mock provider."""
    provider = MagicMock()
    provider.is_available.return_value = True
    return provider


class TestLLMClientIntegration:
    def test_complete_method_builds_messages(self, llm_client, mock_provider):
        """Test that complete() builds the correct message structure."""
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {}
        }
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.complete(
            role="executor",
            system="You are helpful",
            user="Hello",
            context="Background info",
        )
        assert resp.ok is True
        # Verify the messages structure
        call_args = mock_provider.chat_completion.call_args
        messages = call_args[1]["messages"]
        assert len(messages) == 4  # system, context, assistant ack, user
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"
        assert "Background info" in messages[1]["content"]
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"
        assert "Hello" in messages[3]["content"]

    def test_unknown_role_falls_back_to_executor(self, llm_client, mock_provider):
        """Test that unknown roles fall back to executor."""
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {}
        }
        llm_client._registry.register("lmstudio", mock_provider)
        # Patch tracer.error to verify fallback warning was logged
        with patch("core.llm_backend.client.tracer.error") as mock_error:
            resp = llm_client.call(role="unknown_role", messages=[{"role": "user", "content": "test"}])
            assert resp.ok is True
            # Verify fallback warning was triggered
            mock_error.assert_called_once()
            args, _ = mock_error.call_args
            assert "unknown role" in str(args).lower()
