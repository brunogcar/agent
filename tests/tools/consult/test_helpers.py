"""Tests for consult_ops.helpers — shared utilities.

Unit-tests the pure functions in tools/consult_ops/helpers.py in isolation:
  - _estimate_tokens() — tiktoken path + char-count fallback
  - _truncate_context() — truncation trigger, warning message, no-op short path
  - _check_consultor_available() — kill-switch (empty model) + provider-unavailable paths
  - _check_rate_limit() — rate-limit window check
  - _get_consultor_provider() — provider-name lookup
  - _call_consultor() — wrapped llm.complete() call

These tests don't go through the consult facade — they patch the helpers
module's cfg / llm / check_rate_limit symbols directly to verify each helper
returns the correct (ok, error_dict) tuple.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.consult_ops import helpers
from tools.consult_ops.helpers import (
    _MAX_CONTEXT_TOKENS,
    _estimate_tokens,
    _truncate_context,
    _check_consultor_available,
    _check_rate_limit,
    _get_consultor_provider,
    _call_consultor,
)


class TestEstimateTokens:
    """_estimate_tokens — token-count estimation."""

    def test_estimate_tokens_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_non_empty_returns_positive(self):
        text = "Hello world"
        result = _estimate_tokens(text)
        assert isinstance(result, int)
        assert result > 0

    def test_estimate_tokens_fallback_uses_char_count(self):
        """When tiktoken.get_encoding raises, fallback to len(text) // 4."""
        with patch.object(helpers, "_HAS_TIKTOKEN", False):
            text = "abcdefghijkl"  # 12 chars -> 3 tokens at 4 chars/token
            assert _estimate_tokens(text) == 3

    def test_estimate_tokens_with_tiktoken_mock(self):
        """When tiktoken is available, use its encoder.encode() result."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2, 3, 4, 5]
        with patch.object(helpers, "_HAS_TIKTOKEN", True):
            with patch("tiktoken.get_encoding", return_value=mock_encoder):
                assert _estimate_tokens("anything") == 5

    def test_estimate_tokens_tiktoken_failure_falls_back(self):
        """If tiktoken raises inside _estimate_tokens, fall back to char count."""
        with patch.object(helpers, "_HAS_TIKTOKEN", True):
            with patch("tiktoken.get_encoding", side_effect=RuntimeError("nope")):
                text = "abcdefgh"  # 8 chars -> 2 tokens
                assert _estimate_tokens(text) == 2


class TestTruncateContext:
    """_truncate_context — token-aware context truncation."""

    def test_empty_context_returns_empty(self):
        ctx, warnings = _truncate_context("")
        assert ctx == ""
        assert warnings == []

    def test_short_context_not_truncated(self):
        short = "A short string"
        ctx, warnings = _truncate_context(short)
        assert ctx == short
        assert warnings == []

    def test_long_context_truncated_with_warning(self):
        """Long context triggers truncation; warning message includes token counts."""
        long_text = "X" * 20000  # ~5000 tokens at 4 chars/token
        with patch.object(helpers, "_HAS_TIKTOKEN", False):
            ctx, warnings = _truncate_context(long_text, max_tokens=_MAX_CONTEXT_TOKENS)
        assert len(ctx) < len(long_text)
        assert len(warnings) == 1
        assert "truncated" in warnings[0].lower()
        assert str(_MAX_CONTEXT_TOKENS) in warnings[0]

    def test_truncate_respects_custom_max_tokens(self):
        """Caller can override max_tokens."""
        long_text = "Y" * 1000  # ~250 tokens
        with patch.object(helpers, "_HAS_TIKTOKEN", False):
            ctx, warnings = _truncate_context(long_text, max_tokens=50)
        assert len(ctx) == 200  # 50 tokens * 4 chars/token
        assert len(warnings) == 1

    def test_truncate_with_tiktoken_uses_encoder_decode(self):
        """When tiktoken is available, truncate uses encoder.decode on a token slice."""
        mock_encoder = MagicMock()
        # 100 tokens returned; we ask for max_tokens=20
        mock_encoder.encode.return_value = list(range(100))
        mock_encoder.decode.return_value = "TRUNCATED"
        with patch.object(helpers, "_HAS_TIKTOKEN", True):
            with patch("tiktoken.get_encoding", return_value=mock_encoder):
                ctx, warnings = _truncate_context("some long text", max_tokens=20)
        assert ctx == "TRUNCATED"
        mock_encoder.decode.assert_called_once_with(list(range(20)))
        assert len(warnings) == 1


class TestCheckConsultorAvailable:
    """_check_consultor_available — kill-switch + provider availability."""

    def test_available_when_configured(self):
        """Both model set + provider available → ok=True, empty dict."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.consultor_model = "gpt-4o-mini"
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "llm") as mock_llm:
                mock_llm.is_available.return_value = True
                ok, err = _check_consultor_available()
        assert ok is True
        assert err == {}

    def test_disabled_when_model_empty(self):
        """Empty consultor_model → ok=False, status=disabled."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.consultor_model = ""
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "llm") as mock_llm:
                mock_llm.is_available.return_value = True
                ok, err = _check_consultor_available()
        assert ok is False
        assert err["status"] == "disabled"
        assert "CONSULTOR_MODEL" in err["error"]

    def test_disabled_when_model_none(self):
        """None consultor_model → ok=False, status=disabled (kill switch)."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.consultor_model = None
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "llm") as mock_llm:
                mock_llm.is_available.return_value = True
                ok, err = _check_consultor_available()
        assert ok is False
        assert err["status"] == "disabled"

    def test_disabled_when_provider_unavailable(self):
        """Model set but provider unavailable → ok=False, status=disabled."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.consultor_model = "gpt-4o-mini"
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "llm") as mock_llm:
                mock_llm.is_available.return_value = False
                ok, err = _check_consultor_available()
        assert ok is False
        assert err["status"] == "disabled"
        assert "not available" in err["error"].lower()
        assert err["provider"] == "openai"

    def test_disabled_when_model_registry_missing_role(self):
        """model_registry missing 'consultor' key → provider defaults to 'unknown'."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.consultor_model = "gpt-4o-mini"
            mock_cfg.model_registry = {}
            with patch.object(helpers, "llm") as mock_llm:
                mock_llm.is_available.return_value = False
                ok, err = _check_consultor_available()
        assert ok is False
        assert err["status"] == "disabled"
        assert err["provider"] == "unknown"


class TestCheckRateLimit:
    """_check_rate_limit — rate-limit pre-flight check."""

    def test_allowed_when_check_rate_limit_true(self):
        """check_rate_limit returns True → ok=True."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "check_rate_limit", return_value=True):
                ok, err = _check_rate_limit()
        assert ok is True
        assert err == {}

    def test_rate_limited_when_check_rate_limit_false(self):
        """check_rate_limit returns False → ok=False, status=rate_limited."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            with patch.object(helpers, "check_rate_limit", return_value=False):
                ok, err = _check_rate_limit()
        assert ok is False
        assert err["status"] == "rate_limited"
        assert "rate limit" in err["error"].lower()
        assert err["provider"] == "openai"

    def test_uses_consultor_provider_name_as_rate_limit_key(self):
        """check_rate_limit is called with the consultor provider name."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {"consultor": {"provider": "deepseek"}}
            with patch.object(helpers, "check_rate_limit", return_value=True) as mock_rl:
                _check_rate_limit()
        mock_rl.assert_called_once_with("deepseek")


class TestGetConsultorProvider:
    """_get_consultor_provider — provider-name lookup helper."""

    def test_returns_provider_when_configured(self):
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {"consultor": {"provider": "openai"}}
            assert _get_consultor_provider() == "openai"

    def test_returns_unknown_when_role_missing(self):
        """If model_registry is missing 'consultor', fall back to 'unknown'."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {}
            assert _get_consultor_provider() == "unknown"

    def test_returns_unknown_when_registry_empty(self):
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {}
            assert _get_consultor_provider() == "unknown"

    def test_returns_unknown_when_provider_key_missing(self):
        """If 'consultor' dict lacks 'provider', fall back to 'unknown'."""
        with patch.object(helpers, "cfg") as mock_cfg:
            mock_cfg.model_registry = {"consultor": {}}
            assert _get_consultor_provider() == "unknown"


class TestCallConsultor:
    """_call_consultor — wrapped llm.complete() call.

    Centralizes LLM access so action handlers don't reference `llm` directly.
    Patching helpers.llm transparently intercepts this call — patching the
    module attribute works because _call_consultor looks up `llm` in the
    helpers module namespace at call time, NOT at import time.
    """

    def test_calls_llm_complete_with_consultor_role(self):
        """_call_consultor should invoke llm.complete(role='consultor', ...)."""
        mock_response = MagicMock()
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.complete.return_value = mock_response
            result = _call_consultor(system="sys", user="usr", context="ctx", trace_id="tid")
        mock_llm.complete.assert_called_once_with(
            role="consultor",
            system="sys",
            user="usr",
            context="ctx",
            trace_id="tid",
        )
        assert result is mock_response

    def test_uses_default_empty_context_and_trace_id(self):
        """_call_consultor should default context='' and trace_id=''."""
        mock_response = MagicMock()
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.complete.return_value = mock_response
            _call_consultor(system="sys", user="usr")
        mock_llm.complete.assert_called_once_with(
            role="consultor",
            system="sys",
            user="usr",
            context="",
            trace_id="",
        )

    def test_returns_llm_complete_result_unchanged(self):
        """_call_consultor should return whatever llm.complete returns (pass-through)."""
        mock_response = MagicMock(ok=True, text="advice")
        with patch.object(helpers, "llm") as mock_llm:
            mock_llm.complete.return_value = mock_response
            result = _call_consultor(system="sys", user="usr")
        assert result is mock_response
        assert result.ok is True
        assert result.text == "advice"
