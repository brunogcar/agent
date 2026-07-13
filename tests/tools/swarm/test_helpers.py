"""Tests for swarm helpers — _sanitize_error + provider error isolation.

v1.0.1: New file. Regression coverage for P1-1 (Gemini API key leak).
"""
from __future__ import annotations

import httpx
import pytest
from unittest.mock import MagicMock, patch

from tools.swarm_ops.helpers import _sanitize_error, _call_provider
from tools.swarm import swarm


class TestSanitizeError:
    """v1.0.1 (P1-1): _sanitize_error strips secrets from exception strings."""

    def test_strips_gemini_key_from_url(self):
        """Gemini puts the API key in the URL query string (?key=...).
        httpx HTTPStatusError includes the full URL — must be redacted.
        """
        exc = Exception(
            "Client error '429 Too Many Requests' for url "
            "'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=AIzaSyTESTKEY1234567890'"
        )
        sanitized = _sanitize_error(exc)
        assert "AIzaSyTESTKEY1234567890" not in sanitized
        assert "key=<redacted>" in sanitized

    def test_strips_token_from_url(self):
        exc = Exception("GET https://api.example.com/data?token=sk-secret123&foo=1 failed")
        sanitized = _sanitize_error(exc)
        assert "sk-secret123" not in sanitized
        assert "token=<redacted>" in sanitized

    def test_strips_authorization_bearer(self):
        exc = Exception("Request failed. Headers: Authorization: Bearer sk-live-key-abc123")
        sanitized = _sanitize_error(exc)
        assert "sk-live-key-abc123" not in sanitized
        assert "Bearer <redacted>" in sanitized

    def test_strips_x_api_key_header(self):
        exc = Exception("Headers: x-api-key: sk-ant-abc123, content-type: application/json")
        sanitized = _sanitize_error(exc)
        assert "sk-ant-abc123" not in sanitized

    def test_strips_key_from_repr(self):
        """Dict reprs may contain the key under 'key'."""
        exc = Exception("Response was {'key': 'AIzaSyABC', 'error': 'quota'}")
        sanitized = _sanitize_error(exc)
        assert "AIzaSyABC" not in sanitized

    def test_preserves_non_secret_errors(self):
        exc = RuntimeError("deepseek API error")
        assert _sanitize_error(exc) == "deepseek API error"

    def test_preserves_status_codes(self):
        exc = Exception("Client error '429 Too Many Requests' for url '...?key=AIzaSyX'")
        sanitized = _sanitize_error(exc)
        assert "429" in sanitized
        assert "Too Many Requests" in sanitized
        assert "AIzaSyX" not in sanitized

    def test_handles_exception_with_no_str(self):
        """An exception whose __str__ raises should not crash _sanitize_error."""
        class BadExc(Exception):
            def __str__(self):
                raise RuntimeError("broken __str__")

        sanitized = _sanitize_error(BadExc())
        # Should fall back to repr, not crash
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0


class TestCallProviderSanitizesError:
    """v1.0.1 (P1-1): _call_provider must sanitize provider exceptions
    before storing them in the result dict's `error` field.
    """

    def test_gemini_key_not_in_result_error(self, mock_providers_with_key_leak_error):
        """End-to-end: a swarm call whose Gemini provider raises an
        httpx.HTTPStatusError with a key-laden URL must NOT leak the key
        into the result's `error` field (which flows into logs + LLM context).
        """
        mock_llm, leaky_error = mock_providers_with_key_leak_error
        # The key from the leaky_error's request URL
        leaked_key = "AIzaSyTESTKEY1234567890_leaked"

        # Use compare (no synthesis step) so we exercise _call_provider directly.
        result = swarm(action="compare", question="test", timeout=10)

        assert result["status"] == "error"  # all providers failed (only gemini, and it raised)
        # The responses array is attached even on all-failed
        responses = result.get("responses", [])
        assert len(responses) == 1
        assert responses[0]["provider"] == "gemini"
        assert responses[0]["text"] == ""
        # The leaked key must NOT appear anywhere in the error string
        assert leaked_key not in responses[0]["error"], (
            f"Gemini API key leaked into error field: {responses[0]['error']!r}"
        )
        # And not in the top-level error message either
        assert leaked_key not in result.get("error", "")

    def test_provider_exception_caught_not_raised(self):
        """_call_provider must never let an exception propagate — it captures
        all exceptions into the result dict (INSTRUCTIONS.md #7).
        """
        leaky_provider = MagicMock()
        leaky_provider.chat_completion.side_effect = RuntimeError("boom")

        result = _call_provider(
            provider_name="openai",
            model="gpt-4o-mini",
            provider=leaky_provider,
            messages=[{"role": "user", "content": "hi"}],
            timeout=5,
            max_tokens=10,
        )
        assert result["text"] == ""
        assert result["error"] == "boom"
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"

    def test_httpx_error_sanitized_in_call_provider(self):
        """Direct unit test: _call_provider sanitizes httpx errors.

        Mirrors how providers actually raise: response.raise_for_status()
        constructs an HTTPStatusError whose str() includes the full request
        URL — including any ?key=... query param (Gemini).
        """
        request = httpx.Request("POST", "https://api.example.com/v1/chat?key=sk-secret123")
        response = httpx.Response(status_code=500, request=request, text="server error")
        # Use raise_for_status() to get the realistic error message format
        # (includes "for url '...?key=sk-secret123'").
        leaky_error = None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            leaky_error = e
        assert leaky_error is not None

        leaky_provider = MagicMock()
        leaky_provider.chat_completion.side_effect = leaky_error

        result = _call_provider(
            provider_name="gemini",
            model="gemini-1.5-pro",
            provider=leaky_provider,
            messages=[{"role": "user", "content": "hi"}],
            timeout=5,
            max_tokens=10,
        )
        assert result["text"] == ""
        assert "sk-secret123" not in result["error"], (
            f"API key leaked into error: {result['error']!r}"
        )
        assert "key=<redacted>" in result["error"]
