"""
tests/tools/consult/test_consult.py
Unit tests for the explicit consult advisory tool.
Verifies guardrails: kill switch, rate limiting, context truncation, and LLM error handling.
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.consult import consult


@pytest.fixture
def mock_cfg():
    """Mock the config object imported in tools.consult."""
    with patch("tools.consult.cfg") as mock:
        mock.consultor_model = "gpt-4o-mini"
        mock.model_registry = {"consultor": {"provider": "openai"}}
        yield mock


@pytest.fixture
def mock_llm():
    """Mock the LLM client imported in tools.consult."""
    with patch("tools.consult.llm") as mock:
        yield mock


@pytest.fixture
def mock_budget():
    """Mock the rate limiter imported in tools.consult."""
    with patch("tools.consult.check_rate_limit") as mock:
        mock.return_value = True  # Default to allowed
        yield mock


# =============================================================================
# Test Guardrails & Opt-out
# =============================================================================

class TestConsultGuardrails:

    def test_consult_disabled_when_model_blank(self, mock_cfg, mock_budget, mock_llm):
        """Tool should instantly return 'disabled' without calling LLM if model is blank."""
        mock_cfg.consultor_model = None
        
        result = consult(question="What is the meaning of life?")
        
        assert result["status"] == "disabled"
        assert "disabled" in result["error"].lower()
        mock_llm.complete.assert_not_called()

    def test_consult_empty_question(self, mock_cfg, mock_budget, mock_llm):
        """Tool should reject empty or whitespace-only questions."""
        result = consult(question="   ")
        
        assert result["status"] == "error"
        assert "empty" in result["error"].lower()
        mock_llm.complete.assert_not_called()

    def test_consult_rate_limited(self, mock_cfg, mock_budget, mock_llm):
        """Tool should return 'rate_limited' and skip LLM call if budget is exceeded."""
        mock_budget.return_value = False
        
        result = consult(question="Review this architecture.")
        
        assert result["status"] == "rate_limited"
        assert "rate limit" in result["error"].lower()
        mock_llm.complete.assert_not_called()


# =============================================================================
# Test Context Truncation
# =============================================================================

class TestContextTruncation:

    def test_context_truncated_when_too_long(self, mock_cfg, mock_budget, mock_llm):
        """Tool must truncate context > 4000 chars and include a warning."""
        # Setup successful LLM response
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "Architecture looks solid."
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        # Pass a massive context
        long_context = "A" * 5000
        result = consult(question="Review this", context=long_context)
        
        assert result["status"] == "success"
        assert "warning" in result
        assert "truncated" in result["warning"].lower()
        
        # Verify the actual context passed to the LLM was capped
        call_kwargs = mock_llm.complete.call_args[1]
        assert len(call_kwargs["context"]) < 5000

    def test_context_not_truncated_when_short(self, mock_cfg, mock_budget, mock_llm):
        """Tool should pass short context through untouched without warnings."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "OK"
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        short_context = "This is a normal length context."
        result = consult(question="Test", context=short_context)
        
        assert result["status"] == "success"
        assert "warning" not in result
        
        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["context"] == short_context


# =============================================================================
# Test LLM Execution Paths
# =============================================================================

class TestConsultExecution:

    def test_consult_success(self, mock_cfg, mock_budget, mock_llm):
        """Tool should return structured success response on valid LLM call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = "Use a factory pattern here."
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        result = consult(question="How to handle multiple DB connections?")
        
        assert result["status"] == "success"
        assert result["advice"] == "Use a factory pattern here."
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"
        
        # Verify llm.complete was called with the correct role
        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs["role"] == "consultor"

    def test_consult_llm_error(self, mock_cfg, mock_budget, mock_llm):
        """Tool should gracefully handle LLM failures (e.g., timeouts)."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.error = "Connection timed out"
        mock_response.model = "gpt-4o-mini"
        mock_llm.complete.return_value = mock_response

        result = consult(question="Test?")
        
        assert result["status"] == "error"
        assert result["error"] == "Connection timed out"
        assert result["provider"] == "openai"
