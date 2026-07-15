"""Tests for consult advise action — general advisory consultation.

Mirrors the structure of tests/tools/swarm/test_consensus.py. Covers:
  1. Success path (mock LLM returns ok)
  2. Disabled path (consultor_model empty)
  3. Rate limited path
  4. LLM error path
  5. Context truncation
  6. trace_id in response
  7. format param affects system prompt
  8. context_type param affects system prompt
"""
from __future__ import annotations

from unittest.mock import patch

from tools.consult import consult
from tests.tools.consult.conftest import make_mock_response, MockTiktokenEncoder


class TestAdviseSuccess:
    """advise: general advisory consultation."""

    def test_advise_success(self, mock_cfg, mock_llm, mock_budget):
        """Should return advice from consultor role."""
        mock_llm.complete.return_value = make_mock_response(text="Use a factory pattern.")
        result = consult(action="advise", question="How to handle DB?")
        assert result["status"] == "success"
        assert result["action"] == "advise"
        assert result["advice"] == "Use a factory pattern."
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"

        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["role"] == "consultor"
        assert call_kwargs["user"] == "How to handle DB?"

    def test_advise_missing_question(self, mock_cfg, mock_llm, mock_budget):
        """Should fail if question is empty."""
        result = consult(action="advise")
        assert result["status"] == "error"
        assert "question" in result["error"].lower()
        mock_llm.complete.assert_not_called()

    def test_advise_blank_question(self, mock_cfg, mock_llm, mock_budget):
        """Should fail if question is whitespace-only."""
        result = consult(action="advise", question="   ")
        assert result["status"] == "error"
        mock_llm.complete.assert_not_called()


class TestAdviseDisabled:
    """advise: kill-switch paths."""

    def test_advise_disabled_when_model_blank(self, mock_cfg, mock_llm, mock_budget):
        """Should return disabled when CONSULTOR_MODEL is empty."""
        mock_cfg.consultor_model = None
        result = consult(action="advise", question="Test?")
        assert result["status"] == "disabled"
        assert "CONSULTOR_MODEL" in result["error"]
        mock_llm.complete.assert_not_called()

    def test_advise_disabled_when_provider_unavailable(self, mock_cfg, mock_llm, mock_budget):
        """Should return disabled when provider is not available."""
        mock_llm.is_available.return_value = False
        result = consult(action="advise", question="Test?")
        assert result["status"] == "disabled"
        assert "not available" in result["error"].lower()
        mock_llm.complete.assert_not_called()


class TestAdviseRateLimited:
    """advise: rate-limit pre-flight."""

    def test_advise_rate_limited(self, mock_cfg, mock_llm, mock_budget):
        """Should return rate_limited when check_rate_limit denies call."""
        mock_budget.return_value = False
        result = consult(action="advise", question="Review this.")
        assert result["status"] == "rate_limited"
        assert "rate limit" in result["error"].lower()
        mock_llm.complete.assert_not_called()


class TestAdviseLLMError:
    """advise: LLM call failure."""

    def test_advise_llm_error(self, mock_cfg, mock_llm, mock_budget):
        """Should return error when llm.complete.ok is False."""
        mock_llm.complete.return_value = make_mock_response(ok=False, error="Connection timed out")
        result = consult(action="advise", question="Test?")
        assert result["status"] == "error"
        assert result["error"] == "Connection timed out"
        assert result["provider"] == "openai"


class TestAdviseContextTruncation:
    """advise: token-aware context truncation."""

    def test_context_truncated_when_too_long(self, mock_cfg, mock_llm, mock_budget):
        """Long context should be truncated with a warning."""
        mock_llm.complete.return_value = make_mock_response(text="Looks solid.")

        long_context = "A" * 10000
        with patch("tools.consult_ops.helpers._estimate_tokens", return_value=2500):
            with patch("tiktoken.get_encoding", return_value=MockTiktokenEncoder()):
                result = consult(action="advise", question="Review", context=long_context)

        assert result["status"] == "success"
        assert "warnings" in result
        assert "truncated" in result["warnings"][0].lower()
        call_kwargs = mock_llm.complete.call_args[1]
        assert len(call_kwargs["context"]) < 10000

    def test_context_not_truncated_when_short(self, mock_cfg, mock_llm, mock_budget):
        """Short context should be passed through unchanged."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        short_context = "Normal length."
        result = consult(action="advise", question="Test", context=short_context)
        assert result["status"] == "success"
        assert "warnings" not in result
        assert mock_llm.complete.call_args[1]["context"] == short_context


class TestAdviseTraceID:
    """advise: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_llm, mock_budget):
        """trace_id should appear in success response."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        result = consult(action="advise", question="Test?", trace_id="trace-123")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-123"
        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["trace_id"] == "trace-123"

    def test_trace_id_in_error_response(self, mock_cfg, mock_llm, mock_budget):
        """trace_id should appear in error response."""
        mock_cfg.consultor_model = None
        result = consult(action="advise", question="Test?", trace_id="trace-456")
        assert result["status"] == "disabled"
        assert result["trace_id"] == "trace-456"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_llm, mock_budget):
        """trace_id should NOT be added when not provided."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        result = consult(action="advise", question="Test?")
        assert result["status"] == "success"
        assert "trace_id" not in result


class TestAdviseFormat:
    """advise: format param affects system prompt."""

    def test_format_markdown_default(self, mock_cfg, mock_llm, mock_budget):
        """Default format=markdown should not add a format suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        # ADVISE_SYSTEM_PROMPT content should be present
        assert "expert advisory consultant" in system_prompt.lower()
        # No JSON suffix
        assert "JSON" not in system_prompt
        # No bullet_points suffix
        assert "bullet points only" not in system_prompt.lower()

    def test_format_json(self, mock_cfg, mock_llm, mock_budget):
        """format=json should append the JSON format suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", format="json")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "valid JSON" in system_prompt
        assert "summary" in system_prompt
        assert "details" in system_prompt
        assert "recommendations" in system_prompt

    def test_format_bullet_points(self, mock_cfg, mock_llm, mock_budget):
        """format=bullet_points should append the bullet_points suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", format="bullet_points")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "bullet points only" in system_prompt.lower()
        assert "No prose paragraphs" in system_prompt


class TestAdviseContextType:
    """advise: context_type param affects system prompt."""

    def test_context_type_code(self, mock_cfg, mock_llm, mock_budget):
        """context_type=code should append the code modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", context_type="code")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "source code" in system_prompt.lower()
        assert "code quality" in system_prompt.lower()

    def test_context_type_logs(self, mock_cfg, mock_llm, mock_budget):
        """context_type=logs should append the logs modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", context_type="logs")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "log output" in system_prompt.lower()
        assert "error patterns" in system_prompt.lower()

    def test_context_type_architecture(self, mock_cfg, mock_llm, mock_budget):
        """context_type=architecture should append the architecture modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", context_type="architecture")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "system architecture" in system_prompt.lower()
        assert "design patterns" in system_prompt.lower()

    def test_context_type_empty(self, mock_cfg, mock_llm, mock_budget):
        """context_type='' should not append any modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", context_type="")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        # Should NOT contain any of the context-type modifiers
        assert "source code" not in system_prompt.lower()
        assert "log output" not in system_prompt.lower()
        assert "design patterns" not in system_prompt.lower()

    def test_context_type_unknown_silently_ignored(self, mock_cfg, mock_llm, mock_budget):
        """Unknown context_type should silently degrade (no suffix)."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="advise", question="Test?", context_type="nonexistent")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "nonexistent" not in system_prompt.lower()
