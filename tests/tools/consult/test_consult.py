"""
tests/tools/consult/test_consult.py
Unit tests for the explicit consult advisory tool.
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.consult import consult


@pytest.fixture
def mock_cfg():
    with patch("tools.consult.cfg") as mock:
        mock.consultor_model = "gpt-4o-mini"
        mock.model_registry = {"consultor": {"provider": "openai"}}
        yield mock


@pytest.fixture
def mock_llm():
    with patch("tools.consult.llm") as mock:
        mock.is_available.return_value = True
        yield mock


@pytest.fixture
def mock_budget():
    with patch("tools.consult.check_rate_limit") as mock:
        mock.return_value = True
        yield mock


class TestConsultGuardrails:
    def test_consult_disabled_when_model_blank(self, mock_cfg, mock_budget, mock_llm):
        mock_cfg.consultor_model = None
        result = consult(question="Test?")
        assert result["status"] == "disabled"
        mock_llm.complete.assert_not_called()

    def test_consult_disabled_when_provider_unavailable(self, mock_cfg, mock_budget, mock_llm):
        mock_llm.is_available.return_value = False
        result = consult(question="Test?")
        assert result["status"] == "disabled"
        assert "not available" in result["error"].lower()
        mock_llm.complete.assert_not_called()

    def test_consult_empty_question(self, mock_cfg, mock_budget, mock_llm):
        result = consult(question="   ")
        assert result["status"] == "error"
        mock_llm.complete.assert_not_called()

    def test_consult_rate_limited(self, mock_cfg, mock_budget, mock_llm):
        mock_budget.return_value = False
        result = consult(question="Review this.")
        assert result["status"] == "rate_limited"
        mock_llm.complete.assert_not_called()


class TestContextTruncation:
    def test_context_truncated_when_too_long(self, mock_cfg, mock_budget, mock_llm):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "Looks solid."
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        # 10000 chars is ~2500 tokens, which is > 2000
        long_context = "A" * 10000
        result = consult(question="Review", context=long_context)
        
        assert result["status"] == "success"
        assert "warnings" in result
        assert "truncated" in result["warnings"][0].lower()
        
        call_kwargs = mock_llm.complete.call_args[1]
        assert len(call_kwargs["context"]) < 10000

    def test_context_not_truncated_when_short(self, mock_cfg, mock_budget, mock_llm):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "OK"
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        short_context = "Normal length."
        result = consult(question="Test", context=short_context)
        
        assert result["status"] == "success"
        assert "warnings" not in result
        assert mock_llm.complete.call_args[1]["context"] == short_context


class TestConsultExecution:
    def test_consult_success(self, mock_cfg, mock_budget, mock_llm):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "Use a factory pattern."
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        result = consult(question="How to handle DB?")
        
        assert result["status"] == "success"
        assert result["advice"] == "Use a factory pattern."
        assert result["provider"] == "openai"
        assert mock_llm.complete.call_args[1]["role"] == "consultor"

    def test_consult_llm_error(self, mock_cfg, mock_budget, mock_llm):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.error = "Connection timed out"
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        result = consult(question="Test?")
        assert result["status"] == "error"
        assert result["error"] == "Connection timed out"
