"""Unit tests for LLMResponse dataclass."""
from __future__ import annotations

import pytest
from core.llm_backend.response import LLMResponse


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
