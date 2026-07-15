"""Shared fixtures for consult tool tests.

All consult infrastructure is fully mocked — no real API calls to any provider.
Mirrors tests/tools/swarm/conftest.py.

Patches three modules so action handlers can be tested in isolation:
  - tools.consult_ops.helpers.cfg  — consultor_model + model_registry
  - tools.consult_ops.helpers.llm  — is_available() + complete()
  - tools.consult_ops.helpers.check_rate_limit  — True/False toggles
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class MockTiktokenEncoder:
    """Mock encoder that returns 1 token per character, guaranteeing truncation.

    Used by truncation tests so we can deterministically drive the
    _truncate_context() path without depending on real tiktoken behavior.
    """

    def encode(self, text: str) -> list[int]:
        return list(range(len(text)))

    def decode(self, tokens: list[int]) -> str:
        return "A" * len(tokens)


@pytest.fixture
def mock_cfg():
    """Patch the cfg singleton as seen by consult_ops.helpers.

    Default: consultor enabled, provider=openai.
    Tests can mutate `mock.consultor_model = None` to trigger the kill-switch path.
    """
    with patch("tools.consult_ops.helpers.cfg") as mock:
        mock.consultor_model = "gpt-4o-mini"
        mock.model_registry = {"consultor": {"provider": "openai"}}
        yield mock


@pytest.fixture
def mock_llm():
    """Patch the llm singleton as seen by consult_ops.helpers.

    Default: is_available() returns True. Tests can flip to False to trigger
    the 'provider unavailable' disabled path.

    complete() returns a MagicMock by default — individual tests override
    return_value with a mock LLMResponse (ok=True/False, text, model).
    """
    with patch("tools.consult_ops.helpers.llm") as mock:
        mock.is_available.return_value = True
        yield mock


@pytest.fixture
def mock_budget():
    """Patch check_rate_limit as seen by consult_ops.helpers.

    Default: returns True (call allowed). Tests can flip to False to trigger
    the rate-limited path.
    """
    with patch("tools.consult_ops.helpers.check_rate_limit") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_tiktoken():
    """Patch tiktoken.get_encoding to return MockTiktokenEncoder.

    Use this in truncation tests to force deterministic token counts
    (1 token per character) regardless of whether real tiktoken is installed.
    """
    with patch("tools.consult_ops.helpers.tiktoken.get_encoding", return_value=MockTiktokenEncoder()):
        yield


def make_mock_response(*, ok: bool = True, text: str = "OK", model: str = "gpt-4o-mini", error: str = ""):
    """Build a mock LLMResponse-like object for llm.complete.return_value."""
    mock = MagicMock()
    mock.ok = ok
    mock.text = text
    mock.model = model
    mock.error = error
    return mock
