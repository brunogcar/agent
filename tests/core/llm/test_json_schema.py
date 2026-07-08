"""Tests for JSON schema enforcement (LLM v1.2).

Tests that json_schema param:
  - Is passed through to the provider correctly
  - Sets response_format to json_schema type (not json_object)
  - Implies json_mode for parsing (response is parsed as JSON)
  - Takes precedence over json_mode when both are set
  - Defaults to None (backward compatible — existing callers unaffected)

All tests mock the provider — no real LLM calls.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
from core.llm_backend.client import LLMClient


@pytest.fixture
def mock_config():
    """Mock configuration for LLM client."""
    with patch("core.llm_backend.config.cfg") as mock_cfg:
        mock_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        mock_cfg.executor_model = "test-model"
        mock_cfg.model_registry = {
            "executor": {"model": "test-model", "timeout": 120, "provider": "lmstudio"},
            "planner": {"model": "test-model", "timeout": 90, "provider": "lmstudio"},
            "router": {"model": "test-model", "timeout": 15, "provider": "lmstudio"},
        }
        mock_cfg.max_context_tokens = 8000
        yield mock_cfg


@pytest.fixture
def llm_client(mock_config):
    return LLMClient()


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat_completion.return_value = {
        "choices": [{"message": {"content": '{"key": "value"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return provider


# ─────────────────────────────────────────────────────────────────────────────
# json_schema passed to provider correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonSchemaPassedToProvider:
    """json_schema must be passed to provider.chat_completion()."""

    def test_json_schema_passed_through(self, llm_client, mock_provider):
        """When json_schema is provided, it's passed to the provider."""
        llm_client._registry.register("lmstudio", mock_provider)
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        llm_client.complete(
            role="executor",
            system="test",
            user="test",
            json_schema=schema,
        )
        # Verify json_schema was passed to provider
        call_kwargs = mock_provider.chat_completion.call_args
        assert call_kwargs.kwargs.get("json_schema") == schema

    def test_json_schema_none_by_default(self, llm_client, mock_provider):
        """When json_schema is not provided, it defaults to None."""
        llm_client._registry.register("lmstudio", mock_provider)
        llm_client.complete(
            role="executor",
            system="test",
            user="test",
            json_mode=True,
        )
        call_kwargs = mock_provider.chat_completion.call_args
        assert call_kwargs.kwargs.get("json_schema") is None


# ─────────────────────────────────────────────────────────────────────────────
# Provider sets correct response_format
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderResponseFormat:
    """Providers must set response_format correctly for json_schema vs json_mode."""

    def test_lmstudio_json_schema_response_format(self):
        """LM Studio provider sets response_format to json_schema type when schema provided."""
        from core.llm_backend.providers.lmstudio import LMStudioProvider
        provider = LMStudioProvider("http://localhost:1234/v1")

        # Mock _get_client to return a mock (avoids creating real httpx.Client)
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        with patch.object(provider, '_get_client', return_value=mock_client):
            schema = {"type": "object", "properties": {"name": {"type": "string"}}}
            provider.chat_completion(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.5,
                max_tokens=100,
                timeout=30,
                json_mode=False,
                json_schema=schema,
            )

        # Verify response_format is json_schema type
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["schema"] == schema

    def test_lmstudio_json_mode_response_format(self):
        """LM Studio provider uses json_object when json_mode=True, json_schema=None."""
        from core.llm_backend.providers.lmstudio import LMStudioProvider
        provider = LMStudioProvider("http://localhost:1234/v1")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        with patch.object(provider, '_get_client', return_value=mock_client):
            provider.chat_completion(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.5,
                max_tokens=100,
                timeout=30,
                json_mode=True,
                json_schema=None,
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["response_format"]["type"] == "json_object"

    def test_lmstudio_json_schema_takes_precedence(self):
        """When both json_mode and json_schema are set, json_schema wins."""
        from core.llm_backend.providers.lmstudio import LMStudioProvider
        provider = LMStudioProvider("http://localhost:1234/v1")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        with patch.object(provider, '_get_client', return_value=mock_client):
            schema = {"type": "object", "properties": {"x": {"type": "string"}}}
            provider.chat_completion(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.5,
                max_tokens=100,
                timeout=30,
                json_mode=True,
                json_schema=schema,
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["schema"] == schema

    def test_openai_compat_json_schema_response_format(self):
        """OpenAI-compatible provider sets response_format to json_schema type."""
        from core.llm_backend.providers.openai_compat import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider("http://api.example.com", "test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        with patch.object(provider, '_get_client', return_value=mock_client):
            schema = {"type": "object", "properties": {"name": {"type": "string"}}}
            provider.chat_completion(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.5,
                max_tokens=100,
                timeout=30,
                json_mode=False,
                json_schema=schema,
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["response_format"]["type"] == "json_schema"

    def test_no_response_format_when_neither_set(self):
        """When neither json_mode nor json_schema is set, no response_format."""
        from core.llm_backend.providers.lmstudio import LMStudioProvider
        provider = LMStudioProvider("http://localhost:1234/v1")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {},
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        with patch.object(provider, '_get_client', return_value=mock_client):
            provider.chat_completion(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.5,
                max_tokens=100,
                timeout=30,
                json_mode=False,
                json_schema=None,
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert "response_format" not in payload


# ─────────────────────────────────────────────────────────────────────────────
# json_schema implies json_mode for parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonSchemaParsing:
    """json_schema should enable JSON parsing (same as json_mode)."""

    def test_json_schema_response_is_parsed(self, llm_client, mock_provider):
        """When json_schema is provided, the response text is parsed as JSON."""
        llm_client._registry.register("lmstudio", mock_provider)
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        result = llm_client.complete(
            role="executor",
            system="test",
            user="test",
            json_schema=schema,
        )
        # result.parsed should be the parsed JSON dict (not None)
        assert result.parsed is not None
        assert result.parsed == {"key": "value"}

    def test_json_schema_parsed_even_without_json_mode(self, llm_client, mock_provider):
        """json_schema enables parsing even when json_mode=False."""
        llm_client._registry.register("lmstudio", mock_provider)
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        result = llm_client.complete(
            role="executor",
            system="test",
            user="test",
            json_mode=False,
            json_schema=schema,
        )
        # Should still parse because json_schema implies json_mode
        assert result.parsed is not None
        assert result.parsed == {"key": "value"}


# ─────────────────────────────────────────────────────────────────────────────
# Backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonSchemaBackwardCompat:
    """Existing callers that don't use json_schema must work unchanged."""

    def test_json_mode_still_works(self, llm_client, mock_provider):
        """json_mode=True (without json_schema) still works as before."""
        llm_client._registry.register("lmstudio", mock_provider)
        result = llm_client.complete(
            role="executor",
            system="test",
            user="test",
            json_mode=True,
        )
        assert result.ok
        assert result.parsed == {"key": "value"}

    def test_no_json_mode_still_works(self, llm_client, mock_provider):
        """Neither json_mode nor json_schema — plain text response."""
        # Override mock to return plain text
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "plain text response"}}],
            "usage": {},
        }
        llm_client._registry.register("lmstudio", mock_provider)
        result = llm_client.complete(
            role="executor",
            system="test",
            user="test",
        )
        assert result.ok
        assert result.text == "plain text response"
        assert result.parsed is None  # no JSON parsing without json_mode/schema
