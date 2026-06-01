"""
tests/core/llm/test_llm.py
Comprehensive unit tests for the LLM client, focusing on:
P1: Robust JSON extraction (regex-based parsing)
Circuit breaker state machine
Error handling and retry logic
Provider abstraction
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

from core.llm import (
    LLMClient,
    LLMResponse,
    CircuitBreaker,
    LMStudioProvider,
    ProviderRegistry,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """Mock configuration for LLM client.
    
    Phase 1 refactor: cfg is now imported in core.llm_backend.config and 
    core.llm_backend.client, not in core.llm directly.
    """
    with patch("core.llm_backend.config.cfg") as mock_cfg:
        mock_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        mock_cfg.executor_model = "test-model"
        mock_cfg.vision_model = "test-vision-model"
        mock_cfg.model_registry = {
            "executor":  {"model": "test-model", "timeout": 120, "provider": "lmstudio"},
            "planner":   {"model": "test-model", "timeout": 90,  "provider": "lmstudio"},
            "router":    {"model": "test-model", "timeout": 15,  "provider": "lmstudio"},
            "consultor": {"model": "test-model", "timeout": 60,  "provider": "openai"},
        }
        # Phase 5 Context Budgeting requires this to prevent MagicMock comparison errors
        mock_cfg.max_context_tokens = 8000
        yield mock_cfg


@pytest.fixture
def llm_client(mock_config):
    """Create an LLM client with mocked config."""
    return LLMClient()


@pytest.fixture
def mock_provider():
    """Create a mock provider."""
    provider = Mock(spec=LMStudioProvider)
    provider.is_available.return_value = True
    return provider


# =============================================================================
# Test LLMResponse
# =============================================================================

class TestLLMResponse:

    def test_from_error(self):
        """Test error response creation."""
        resp = LLMResponse.from_error("executor", "test-model", "Timeout", elapsed=5.0)
        assert resp.ok is False
        assert resp.error == "Timeout"
        assert resp.role == "executor"
        assert resp.model == "test-model"
        assert resp.elapsed == 5.0
        assert resp.text == ""
        assert resp.usage == {"prompt": 0, "completion": 0, "total": 0}

    def test_success_response(self):
        """Test successful response structure."""
        resp = LLMResponse(
            text="Hello world",
            role="executor",
            model="test-model",
            usage={"prompt": 10, "completion": 5, "total": 15},
            elapsed=1.5,
            parsed={"key": "value"},
            ok=True,
        )
        assert resp.ok is True
        assert resp.text == "Hello world"
        assert resp.parsed == {"key": "value"}


# =============================================================================
# Test Circuit Breaker
# =============================================================================

class TestCircuitBreaker:

    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        assert breaker.can_execute() is True
        state = breaker.get_state_info()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0

    def test_opens_after_threshold_failures(self):
        """Circuit opens after consecutive failures."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.can_execute() is True
        breaker.record_failure()  # 3rd failure
        assert breaker.can_execute() is False
        state = breaker.get_state_info()
        assert state["state"] == "open"
        assert state["failure_count"] == 3

    def test_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.can_execute() is False
        import time
        breaker._last_failure_time = time.time() - 2  # 2 seconds ago
        assert breaker.can_execute() is True
        state = breaker.get_state_info()
        assert state["state"] == "half-open"

    def test_closes_on_success_in_half_open(self):
        """Successful call in HALF_OPEN closes the circuit."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        import time
        breaker._last_failure_time = time.time() - 2
        breaker.can_execute()  # Transitions to HALF_OPEN
        breaker.record_success()
        state = breaker.get_state_info()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0

    def test_reopens_on_failure_in_half_open(self):
        """Failed call in HALF_OPEN reopens the circuit."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        breaker.record_failure()
        breaker.record_failure()
        import time
        breaker._last_failure_time = time.time() - 2
        breaker.can_execute()  # Transitions to HALF_OPEN
        breaker.record_failure()
        state = breaker.get_state_info()
        assert state["state"] == "open"
        assert state["failure_count"] == breaker.failure_threshold


# =============================================================================
# Test JSON Extraction (P1 Fix)
# =============================================================================

class TestJSONExtraction:
    """Test the robust regex-based JSON parsing in _parse_response."""

    def test_clean_json(self):
        """Test parsing clean JSON without any wrapping."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value", "number": 42}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value", "number": 42}

    def test_json_in_markdown_fence(self):
        """Test parsing JSON wrapped in ```json code blocks."""
        raw = {
            "choices": [{"message": {"content": '```json\n{"key": "value"}\n```'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_in_generic_fence(self):
        """Test parsing JSON wrapped in ``` code blocks."""
        raw = {
            "choices": [{"message": {"content": '```\n{"key": "value"}\n```'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_conversational_prefix(self):
        """Test parsing JSON with text before it."""
        raw = {
            "choices": [{"message": {"content": 'Here is the result:\n{"key": "value"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_conversational_suffix(self):
        """Test parsing JSON with text after it."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"}\n\nHope this helps!'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_surrounding_text(self):
        """Test parsing JSON with text before and after."""
        raw = {
            "choices": [{"message": {"content": 'Sure! Here you go:\n\n{"status": "success", "data": [1, 2, 3]}\n\nLet me know if you need anything else.'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"status": "success", "data": [1, 2, 3]}

    def test_nested_json_object(self):
        """Test parsing nested JSON structures."""
        raw = {
            "choices": [{"message": {"content": '{"outer": {"inner": "value"}, "array": [1, 2, {"nested": true}]}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed["outer"]["inner"] == "value"
        assert resp.parsed["array"][2]["nested"] is True

    def test_json_array(self):
        """Test parsing JSON arrays."""
        raw = {
            "choices": [{"message": {"content": '[1, 2, 3, {"key": "value"}]'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == [1, 2, 3, {"key": "value"}]

    def test_malformed_json_graceful_failure(self):
        """Test that malformed JSON doesn't crash, just returns None."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"'}}],  # Missing closing brace
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed is None  # Graceful degradation

    def test_no_json_in_response(self):
        """Test response with no JSON at all."""
        raw = {
            "choices": [{"message": {"content": 'This is just plain text with no JSON.'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed is None

    def test_json_mode_false_skips_parsing(self):
        """Test that json_mode=False skips JSON parsing entirely."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=False)
        assert resp.ok is True
        assert resp.parsed is None  # Not parsed because json_mode=False
        assert resp.text == '{"key": "value"}'

    def test_json_with_backticks_in_string(self):
        """Test JSON containing backticks in string values."""
        raw = {
            "choices": [{"message": {"content": '{"code": "```python\\nprint(\\"hello\\")\\n```"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert "```python" in resp.parsed["code"]


# =============================================================================
# Test LLMClient Error Handling
# =============================================================================

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


# =============================================================================
# Test Provider Registry
# =============================================================================

class TestProviderRegistry:

    def test_register_and_get(self):
        """Test provider registration and retrieval."""
        registry = ProviderRegistry()
        provider = Mock(spec=LMStudioProvider)
        registry.register("test", provider)
        retrieved = registry.get("test")
        assert retrieved is provider

    def test_get_nonexistent_raises(self):
        """Test that getting a non-existent provider raises KeyError."""
        registry = ProviderRegistry()
        with pytest.raises(KeyError, match="Provider 'nonexistent' not registered"):
            registry.get("nonexistent")

    def test_available_providers(self):
        """Test listing available providers."""
        registry = ProviderRegistry()
        registry.register("provider1", Mock())
        registry.register("provider2", Mock())
        available = registry.available()
        assert "provider1" in available
        assert "provider2" in available


# =============================================================================
# Test LLMClient Integration
# =============================================================================

class TestLLMClientIntegration:

    def test_complete_method_builds_messages(self, llm_client, mock_provider):
        """Test that complete() builds the correct message structure."""
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {}
        }
        llm_client._registry.register("lmstudio", mock_provider)
        resp = llm_client.complete(
            role="executor",
            system="You are helpful",
            user="Hello",
            context="Background info",
        )
        assert resp.ok is True
        # Verify the messages structure
        call_args = mock_provider.chat_completion.call_args
        messages = call_args[1]["messages"]
        assert len(messages) == 4  # system, context, assistant ack, user
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"
        assert "Background info" in messages[1]["content"]
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"
        assert "Hello" in messages[3]["content"]

    def test_unknown_role_falls_back_to_executor(self, llm_client, mock_provider):
        """Test that unknown roles fall back to executor."""
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {}
        }
        llm_client._registry.register("lmstudio", mock_provider)
        # Patch tracer.error to verify fallback warning was logged
        # Phase 1 refactor: tracer is imported in core.llm_backend.client
        with patch("core.llm_backend.client.tracer.error") as mock_error:
            resp = llm_client.call(role="unknown_role", messages=[{"role": "user", "content": "test"}])
        assert resp.ok is True
        # Verify fallback warning was triggered
        mock_error.assert_called_once()
        args, _ = mock_error.call_args
        assert "unknown role" in str(args).lower()
class TestNetworkPartitionsAndSchemaDrift:
    def test_malformed_html_response(self, llm_client, mock_provider):
        """Provider returns HTML (e.g., Cloudflare block) instead of JSON."""
        mock_provider.chat_completion.return_value = "<html><body>502 Bad Gateway</body></html>"
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
