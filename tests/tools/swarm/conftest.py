"""Shared fixtures for swarm tool tests.

All swarm infrastructure is fully mocked — no real API calls to any provider.

v1.0.1:
  - mock_llm_empty_registry now scopes os.getenv overrides to *_BASE_MODEL
    keys only (was patching os.getenv globally with return_value="").
  - Added mock_provider_with_response for building controlled per-provider
    responses (used by vote classification tests).
  - Added mock_providers_with_key_leak_error for the Gemini-key-leak
    regression test (P1-1).
  - Added mock_providers_with_slow_one for the race latency test (P1-2).
"""
from __future__ import annotations

import time

import pytest
from unittest.mock import MagicMock, patch


def _build_provider(name: str, response_text: str, *, tokens: int = 15, side_effect=None):
    """Construct a mock provider with a controlled chat_completion response."""
    mock_provider = MagicMock()
    if side_effect is not None:
        mock_provider.chat_completion.side_effect = side_effect
    else:
        mock_provider.chat_completion.return_value = {
            "choices": [{"message": {"content": response_text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": tokens},
        }
    mock_provider.is_available.return_value = True
    return mock_provider


@pytest.fixture
def mock_providers():
    """Mock 3 cloud providers in llm._registry._providers.

    Returns a dict of {name: mock_provider} for assertion.
    """
    providers = {}

    for name, model in [("openai", "gpt-4o-mini"), ("deepseek", "deepseek-chat"), ("claude", "claude-3-5-haiku-20241022")]:
        mock_provider = _build_provider(name, f"Response from {name}")
        providers[name] = mock_provider

    return providers


@pytest.fixture
def mock_llm_registry(mock_providers):
    """Patch llm._registry._providers with mock providers + mock os.getenv for BASE_MODEL.

    Also patches llm.complete (used by consensus synthesis) to return a mock response.
    """
    import os

    # Patch the llm singleton's registry
    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),  # should be skipped by swarm
            **mock_providers,
        }
        # Mock llm.complete for consensus synthesis
        mock_synthesis = MagicMock()
        mock_synthesis.ok = True
        mock_synthesis.text = "Synthesized answer combining all responses."
        mock_llm.complete.return_value = mock_synthesis

        # Patch os.getenv to return model names for each provider
        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "OPENAI_BASE_MODEL":
                return "gpt-4o-mini"
            elif key == "DEEPSEEK_BASE_MODEL":
                return "deepseek-chat"
            elif key == "CLAUDE_BASE_MODEL":
                return "claude-3-5-haiku-20241022"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm


@pytest.fixture
def mock_llm_empty_registry():
    """Patch llm with NO cloud providers (only lmstudio).

    Used to test 'no providers configured' error paths.

    v1.0.1: os.getenv now scoped to *_BASE_MODEL keys only. The previous
    global `patch("os.getenv", return_value="")` would mask any other env
    var read during the test, making this fixture fragile.
    """
    import os

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),  # only local — should be skipped
        }

        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            # Only *_BASE_MODEL is relevant to swarm's _get_available_providers.
            # Return empty for all of them; pass through everything else.
            if key.endswith("_BASE_MODEL"):
                return ""
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm


@pytest.fixture
def mock_failing_providers():
    """Mock providers that all raise exceptions.

    Used to test 'all providers failed' error paths.
    """
    import os

    providers = {}
    for name, model in [("openai", "gpt-4o-mini"), ("deepseek", "deepseek-chat")]:
        mock_provider = _build_provider(name, "", side_effect=RuntimeError(f"{name} API error"))
        providers[name] = mock_provider

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),
            **providers,
        }

        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "OPENAI_BASE_MODEL":
                return "gpt-4o-mini"
            elif key == "DEEPSEEK_BASE_MODEL":
                return "deepseek-chat"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm


@pytest.fixture
def make_vote_providers():
    """Factory fixture: build a mock_llm registry with controlled per-provider
    response texts.

    Usage:
        def test_x(make_vote_providers):
            llm = make_vote_providers({
                "openai": "YES",
                "claude": "YES",
                "deepseek": "NO",
            })
            next(llm)  # enter the patched context
            result = swarm(action="vote", question="...")
            ...

    A response value of ``None`` means the provider is configured but its
    chat_completion raises (used to test single_response / partial-failure
    agreement classification).

    v1.0.1: Added for the vote classification tests (P2-1, P2-2, P2-3).
    """
    import os

    def _build(responses: dict[str, str | None], models: dict[str, str] | None = None):
        models = models or {}
        providers = {}
        for name, text in responses.items():
            if text is None:
                providers[name] = _build_provider(
                    name, "", side_effect=RuntimeError(f"{name} down")
                )
            else:
                providers[name] = _build_provider(name, text)

        with patch("core.llm.llm") as mock_llm:
            mock_llm._registry._providers = {
                "lmstudio": MagicMock(),
                **providers,
            }
            mock_synthesis = MagicMock()
            mock_synthesis.ok = True
            mock_synthesis.text = "synthesized"
            mock_llm.complete.return_value = mock_synthesis

            original_getenv = os.getenv
            def _mock_getenv(key, default=""):
                if key.endswith("_BASE_MODEL"):
                    provider_name = key[:-len("_BASE_MODEL")].lower()
                    return models.get(provider_name, f"{provider_name}-model")
                return original_getenv(key, default)

            with patch("os.getenv", side_effect=_mock_getenv):
                yield mock_llm

    return _build


@pytest.fixture
def mock_providers_with_key_leak_error():
    """Mock a Gemini provider whose chat_completion raises an httpx
    HTTPStatusError whose string contains the API key in the URL.

    v1.0.1: Regression test for P1-1 — without _sanitize_error(), the key
    would flow into the swarm result's `error` field and into logs + LLM
    context.
    """
    import os

    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    # Build an httpx.HTTPStatusError with a key-laden URL, mirroring how
    # Gemini raises (gemini.py:121 response.raise_for_status()). We use
    # raise_for_status() so the error message includes the full URL (the
    # realistic format), rather than hand-rolling a bare message string.
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=AIzaSyTESTKEY1234567890_leaked")
    response = httpx.Response(
        status_code=429,
        request=request,
        text='{"error": {"code": 429, "message": "Quota exceeded"}}',
    )
    leaky_error = None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        leaky_error = e
    assert leaky_error is not None

    gemini_provider = _build_provider("gemini", "", side_effect=leaky_error)

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),
            "gemini": gemini_provider,
        }

        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "GEMINI_BASE_MODEL":
                return "gemini-1.5-pro"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm, leaky_error


@pytest.fixture
def mock_providers_with_slow_one():
    """Mock 2 providers: one returns after 0.3s, one sleeps 2s.

    v1.0.1: Regression test for P1-2 — race must return as soon as the fast
    provider responds, without waiting for the slow one.

    Both providers use real ``time.sleep`` (not instant MagicMock returns) so
    that both ThreadPoolExecutor workers are genuinely running when the fast
    one finishes. This ensures the slow future is RUNNING (not PENDING) when
    the winner is found — which is the exact condition under which v1.0's
    ``shutdown(wait=True)`` blocked for the full slow duration. If the fast
    provider returned instantly, v1.0's ``f.cancel()`` would succeed on the
    still-pending slow future and the bug wouldn't reproduce.
    """
    import os

    def fast_call(*args, **kwargs):
        time.sleep(0.3)
        return {"choices": [{"message": {"content": "fast response"}}], "usage": {"total_tokens": 5}}

    def slow_call(*args, **kwargs):
        time.sleep(2)
        return {"choices": [{"message": {"content": "slow response"}}], "usage": {"total_tokens": 5}}

    fast_provider = MagicMock()
    fast_provider.chat_completion.side_effect = fast_call
    fast_provider.is_available.return_value = True
    slow_provider = MagicMock()
    slow_provider.chat_completion.side_effect = slow_call
    slow_provider.is_available.return_value = True

    with patch("core.llm.llm") as mock_llm:
        mock_llm._registry._providers = {
            "lmstudio": MagicMock(),
            "openai": fast_provider,
            "deepseek": slow_provider,
        }

        original_getenv = os.getenv
        def _mock_getenv(key, default=""):
            if key == "OPENAI_BASE_MODEL":
                return "gpt-4o-mini"
            elif key == "DEEPSEEK_BASE_MODEL":
                return "deepseek-chat"
            return original_getenv(key, default)

        with patch("os.getenv", side_effect=_mock_getenv):
            yield mock_llm
