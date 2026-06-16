"""Unit tests for LLMClient error handling and retry logic."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

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


class TestLLMClientErrorHandling:
    def test_timeout_exception(self, llm_client, mock_provider):
        """Test handling of timeout exceptions."""
        mock_provider.chat_completion.side_effect = httpx.TimeoutException("Timeout")
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is False
        assert "Timeout" in resp.error

    def test_connection_error(self, llm_client, mock_provider):
        """Test handling of connection errors."""
        mock_provider.chat_completion.side_effect = httpx.ConnectError("Connection refused")
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is False
        assert "Cannot connect" in resp.error

    def test_http_status_error_non_429(self, llm_client, mock_provider):
        """Test handling of non-429 HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        error = httpx.HTTPStatusError("Error", request=Mock(), response=mock_response)
        mock_provider.chat_completion.side_effect = error
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is False
        assert "500" in resp.error

    def test_retry_on_429(self, llm_client, mock_provider):
        """Test retry logic on 429 rate limit."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        error = httpx.HTTPStatusError("Error", request=Mock(), response=mock_response)
        # First two calls fail with 429, third succeeds
        mock_provider.chat_completion.side_effect = [
            error,
            error,
            {"choices": [{"message": {"content": "success"}}], "usage": {}}
        ]
        llm_client._registry.register("lmstudio", mock_provider)
        # Patch sleep to speed up test
        with patch("time.sleep"):
            resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is True
        assert resp.text == "success"
        assert mock_provider.chat_completion.call_count == 3


class TestNetworkPartitionsAndSchemaDrift:
    def test_malformed_html_response(self, llm_client, mock_provider):
        """Provider returns HTML (e.g., Cloudflare block) instead of JSON."""
        mock_provider.chat_completion.return_value = "502 Bad Gateway"
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is False
        assert "error" in resp.error.lower() or "502" in resp.error

    def test_missing_choices_field(self, llm_client, mock_provider):
        """Provider returns valid JSON but missing expected 'choices' key."""
        mock_provider.chat_completion.return_value = {"usage": {}}
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.call(role="executor", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is False
        assert "error" in resp.error.lower()
