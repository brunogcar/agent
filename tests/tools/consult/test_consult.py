"""
❌ tests/tools/consult/test_consult.py
Unit tests for the explicit consult advisory tool.
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.consult import consult


class MockTiktokenEncoder:
    """Mock encoder that returns 1 token per character, guaranteeing truncation."""
    def encode(self, text: str) -> list[int]:
        return list(range(len(text)))

    def decode(self, tokens: list[int]) -> str:
        return "A" * len(tokens)


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
        result = consult(question=" ")
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

        long_context = "A" * 10000
        with patch("tools.consult._estimate_tokens", return_value=2500):
            with patch("tiktoken.get_encoding", return_value=MockTiktokenEncoder()):
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


class TestPhase5CHardening:
    def test_concurrent_rate_limiter_stress(self, mock_cfg, mock_budget, mock_llm):
        """Verify rate limiter holds up under concurrent burst."""
        from core.llm_backend.budget import check_rate_limit
        import threading

        results = []
        def make_call():
            results.append(check_rate_limit("openai", max_calls=3, period=60))

        threads = [threading.Thread(target=make_call) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert sum(results) == 3

    def test_unicode_context_truncation(self, mock_cfg, mock_budget, mock_llm):
        """Ensure truncation doesn't break mid-unicode character."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "OK"
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        unicode_context = "Hello " + "世界" * 2000
        result = consult(question="Test", context=unicode_context)
        assert result["status"] == "success"
