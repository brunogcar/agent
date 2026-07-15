"""Tests for consult explain action — concept explanation.

Mirrors the structure of test_advise.py / test_review.py. Covers:
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


class TestExplainSuccess:
    """explain: concept explanation."""

    def test_explain_success(self, mock_cfg, mock_llm, mock_budget):
        """Should return explanation from consultor role."""
        mock_llm.complete.return_value = make_mock_response(text="RAG is like...")
        result = consult(action="explain", question="What is RAG?")
        assert result["status"] == "success"
        assert result["action"] == "explain"
        assert result["explanation"] == "RAG is like..."
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"

        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["role"] == "consultor"
        assert call_kwargs["user"] == "What is RAG?"

    def test_explain_missing_question(self, mock_cfg, mock_llm, mock_budget):
        """Should fail if question is empty."""
        result = consult(action="explain")
        assert result["status"] == "error"
        assert "question" in result["error"].lower()
        mock_llm.complete.assert_not_called()

    def test_explain_blank_question(self, mock_cfg, mock_llm, mock_budget):
        """Should fail if question is whitespace-only."""
        result = consult(action="explain", question="   ")
        assert result["status"] == "error"
        mock_llm.complete.assert_not_called()


class TestExplainDisabled:
    """explain: kill-switch paths."""

    def test_explain_disabled_when_model_blank(self, mock_cfg, mock_llm, mock_budget):
        """Should return disabled when CONSULTOR_MODEL is empty."""
        mock_cfg.consultor_model = None
        result = consult(action="explain", question="Explain CAP theorem?")
        assert result["status"] == "disabled"
        mock_llm.complete.assert_not_called()

    def test_explain_disabled_when_provider_unavailable(self, mock_cfg, mock_llm, mock_budget):
        """Should return disabled when provider is not available."""
        mock_llm.is_available.return_value = False
        result = consult(action="explain", question="Explain CAP theorem?")
        assert result["status"] == "disabled"
        mock_llm.complete.assert_not_called()


class TestExplainRateLimited:
    """explain: rate-limit pre-flight."""

    def test_explain_rate_limited(self, mock_cfg, mock_llm, mock_budget):
        """Should return rate_limited when check_rate_limit denies call."""
        mock_budget.return_value = False
        result = consult(action="explain", question="Explain X.")
        assert result["status"] == "rate_limited"
        mock_llm.complete.assert_not_called()


class TestExplainLLMError:
    """explain: LLM call failure."""

    def test_explain_llm_error(self, mock_cfg, mock_llm, mock_budget):
        """Should return error when llm.complete.ok is False."""
        mock_llm.complete.return_value = make_mock_response(ok=False, error="timeout")
        result = consult(action="explain", question="Explain?")
        assert result["status"] == "error"
        assert result["error"] == "timeout"


class TestExplainContextTruncation:
    """explain: token-aware context truncation."""

    def test_context_truncated_when_too_long(self, mock_cfg, mock_llm, mock_budget):
        """Long context should be truncated with a warning."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        long_context = "C" * 10000
        with patch("tools.consult_ops.helpers._estimate_tokens", return_value=2500):
            with patch("tiktoken.get_encoding", return_value=MockTiktokenEncoder()):
                result = consult(action="explain", question="Explain", context=long_context)
        assert result["status"] == "success"
        assert "warnings" in result
        assert "truncated" in result["warnings"][0].lower()
        call_kwargs = mock_llm.complete.call_args[1]
        assert len(call_kwargs["context"]) < 10000

    def test_context_not_truncated_when_short(self, mock_cfg, mock_llm, mock_budget):
        """Short context should be passed through unchanged."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        short_context = "Some background."
        result = consult(action="explain", question="Explain", context=short_context)
        assert result["status"] == "success"
        assert "warnings" not in result
        assert mock_llm.complete.call_args[1]["context"] == short_context


class TestExplainTraceID:
    """explain: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_llm, mock_budget):
        """trace_id should appear in success response."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        result = consult(action="explain", question="Explain?", trace_id="trace-exp-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-exp-1"
        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["trace_id"] == "trace-exp-1"

    def test_trace_id_in_error_response(self, mock_cfg, mock_llm, mock_budget):
        """trace_id should appear in disabled response."""
        mock_cfg.consultor_model = None
        result = consult(action="explain", question="Explain?", trace_id="trace-exp-2")
        assert result["status"] == "disabled"
        assert result["trace_id"] == "trace-exp-2"


class TestExplainFormat:
    """explain: format param affects system prompt."""

    def test_format_markdown_default(self, mock_cfg, mock_llm, mock_budget):
        """Default format=markdown should not add a format suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "technical educator" in system_prompt.lower()
        assert "JSON" not in system_prompt

    def test_format_json(self, mock_cfg, mock_llm, mock_budget):
        """format=json should append the JSON format suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", format="json")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "valid JSON" in system_prompt

    def test_format_bullet_points(self, mock_cfg, mock_llm, mock_budget):
        """format=bullet_points should append the bullet_points suffix."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", format="bullet_points")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "bullet points only" in system_prompt.lower()


class TestExplainContextType:
    """explain: context_type param affects system prompt."""

    def test_context_type_code(self, mock_cfg, mock_llm, mock_budget):
        """context_type=code should append the code modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", context_type="code")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "source code" in system_prompt.lower()

    def test_context_type_logs(self, mock_cfg, mock_llm, mock_budget):
        """context_type=logs should append the logs modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", context_type="logs")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "log output" in system_prompt.lower()

    def test_context_type_architecture(self, mock_cfg, mock_llm, mock_budget):
        """context_type=architecture should append the architecture modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", context_type="architecture")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "system architecture" in system_prompt.lower()

    def test_context_type_empty(self, mock_cfg, mock_llm, mock_budget):
        """context_type='' should not append any modifier."""
        mock_llm.complete.return_value = make_mock_response(text="OK")
        consult(action="explain", question="Test?", context_type="")
        system_prompt = mock_llm.complete.call_args[1]["system"]
        assert "source code" not in system_prompt.lower()
