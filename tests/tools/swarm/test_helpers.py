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


class TestSanitizeErrorBroadened:
    """v1.0.2 (P2-1 cross-LLM): Broader secret-pattern coverage.

    v1.0.1 covered URL query params, Authorization: Bearer, x-api-key, and
    dict reprs. v1.0.2 adds: camelCase JSON keys (apiKey), hyphenated
    (api-key), bare provider-prefix keys in prose (AIzaSy..., sk-ant-...,
    sk-...), and base64-friendly fallback chars (+, /, =).
    """

    def test_strips_camelcase_apikey_in_json(self):
        exc = Exception('Response: {"apiKey": "sk-test-key-1234567890123"}')
        sanitized = _sanitize_error(exc)
        assert "sk-test-key-1234567890123" not in sanitized

    def test_strips_hyphenated_api_key_header(self):
        exc = Exception("api-key: sk-ant-api03-abcdefghij1234567890")
        sanitized = _sanitize_error(exc)
        assert "sk-ant-api03-abcdefghij1234567890" not in sanitized

    def test_strips_access_token_camelcase(self):
        exc = Exception('{"accessToken": "ya29.test-token-123456789012"}')
        sanitized = _sanitize_error(exc)
        assert "ya29.test-token-123456789012" not in sanitized

    def test_strips_bare_google_key_in_prose(self):
        """Keys appearing in prose without a `key=` prefix (e.g., 'with key AIzaSyD...').

        v1.0.2 (P2-1): provider-prefix catch-all handles this.
        """
        exc = Exception("Authentication failed with API key AIzaSyD_fake-google-key-1234567890aaa")
        sanitized = _sanitize_error(exc)
        assert "AIzaSyD_fake-google-key-1234567890aaa" not in sanitized

    def test_strips_bare_anthropic_key_in_prose(self):
        exc = Exception("using token sk-ant-api03-fake-anthropic-key-1234567890")
        sanitized = _sanitize_error(exc)
        assert "sk-ant-api03-fake-anthropic-key-1234567890" not in sanitized

    def test_strips_bare_openai_key_in_prose(self):
        exc = Exception("rejected key sk-fakeopenaikey123456789012345")
        sanitized = _sanitize_error(exc)
        assert "sk-fakeopenaikey123456789012345" not in sanitized

    def test_fallback_handles_base64_chars(self):
        """v1.0.2 (P2-1): fallback regex now includes +, /, = for base64 tokens."""
        # A base64-looking token after 'token='
        exc = Exception("token=eyJhbGciOiJIUzI1NiJ9+abc/def==")
        sanitized = _sanitize_error(exc)
        assert "eyJhbGciOiJIUzI1NiJ9+abc/def==" not in sanitized

    def test_fallback_threshold_lowered_to_16(self):
        """v1.0.2 (P2-1): fallback now redacts 16+ char tokens (was 32+).
        Some providers issue 20-28 char keys that v1.0.1 would miss.

        Tests the fallback regex with a quoted format (e.g., key: "short20...")
        which is what the fallback pattern matches. URL-style ?key=... is
        covered by the first _SECRET_PATTERNS entry (tested elsewhere).
        """
        # 20-char key in a quoted dict format — exercises the fallback regex
        exc = Exception('{"key": "short20charkey1234"}')
        sanitized = _sanitize_error(exc)
        assert "short20charkey1234" not in sanitized


class TestSanitizeErrorSelfGuard:
    """v1.0.2 (P1-4 cross-LLM): _sanitize_error must never itself raise.

    A pathological exception whose __str__ AND __repr__ both raise must not
    crash the action (which would break per-provider error isolation).
    """

    def test_pathological_exception_returns_safe_string(self):
        class PathologicalExc(Exception):
            def __str__(self):
                raise RuntimeError("str broken")

            def __repr__(self):
                raise RuntimeError("repr broken")

        sanitized = _sanitize_error(PathologicalExc("unused"))
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0
        # Should fall back to a safe type-name string
        assert "PathologicalExc" in sanitized

    def test_sanitize_never_raises_on_any_input(self):
        """Fuzz-ish: various weird exception objects must not crash."""
        weird_inputs = [
            Exception(),
            RuntimeError(""),
            ValueError(None),
            TypeError(),
            KeyError("missing"),
            AttributeError(),
        ]
        for exc in weird_inputs:
            result = _sanitize_error(exc)
            assert isinstance(result, str), f"_sanitize_error returned non-str for {exc!r}"


class TestCallAllProvidersTimeout:
    """v1.0.2 (P1-1 cross-LLM): _call_all_providers must not hang on timeout.

    The v1.0.1 implementation used `with ThreadPoolExecutor(...)` +
    `as_completed(timeout=...)`. If as_completed raised TimeoutError, the
    `with` block's __exit__ called shutdown(wait=True), blocking forever on
    a hanging provider. This affected consensus, vote, and compare.

    The v1.0.2 rewrite mirrors _call_providers_race: explicit executor +
    try/except TimeoutError + finally: shutdown(wait=False, cancel_futures=True).
    """

    def test_call_all_providers_does_not_hang_on_slow_provider(self):
        """If one provider hangs, _call_all_providers must still return within
        the timeout window, not block forever on shutdown(wait=True).
        """
        import time as _time
        from unittest.mock import MagicMock, patch
        import os
        from tools.swarm_ops.helpers import _call_all_providers

        def fast_call(*a, **k):
            return {"choices": [{"message": {"content": "fast"}}], "usage": {"total_tokens": 5}}

        def hanging_call(*a, **k):
            # Sleep longer than the as_completed window (timeout+10).
            # With timeout=1, the window is 11s; sleep 30s to guarantee the
            # provider is still running when as_completed times out.
            _time.sleep(30)
            return {"choices": [{"message": {"content": "never"}}], "usage": {"total_tokens": 5}}

        fast = MagicMock()
        fast.chat_completion.side_effect = fast_call
        hanging = MagicMock()
        hanging.chat_completion.side_effect = hanging_call

        providers = [("openai", "m1", fast), ("slow", "m2", hanging)]

        start = _time.monotonic()
        # timeout=1 + the +10s buffer in as_completed = ~11s max. Under the
        # v1.0.1 bug, shutdown(wait=True) would block the full 30s of the
        # hanging sleep. Under v1.0.2, shutdown(wait=False) returns immediately
        # after as_completed times out at ~11s.
        results = _call_all_providers(
            providers, "sys", "q", "", timeout=1, max_tokens=10
        )
        elapsed = _time.monotonic() - start

        # Should return in ~11s (as_completed timeout), NOT 30s+ (hanging sleep).
        # Allow generous slack for CI.
        assert elapsed < 20, (
            f"_call_all_providers took {elapsed:.1f}s — v1.0.1 bug: shutdown(wait=True) "
            f"blocked on the hanging provider."
        )
        # Both providers should have a result entry
        assert len(results) == 2
        # The fast provider should have succeeded
        fast_result = next(r for r in results if r["provider"] == "openai")
        assert fast_result["text"] == "fast"
        # The hanging provider should be marked as timeout (no real response)
        slow_result = next(r for r in results if r["provider"] == "slow")
        assert slow_result["text"] == "", f"hanging provider returned text: {slow_result['text']!r}"
        assert slow_result["error"] == "timeout"
