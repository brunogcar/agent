"""Shared fixtures for vision tool tests.

All vision infrastructure is fully mocked — no real LLM calls, no real HTTP
downloads, no real SSRF DNS resolution.

Mirrors tests/tools/consult/conftest.py. Patches four modules so action
handlers can be tested in isolation:
  - tools.vision_ops.helpers.cfg        — vision_model kill switch
  - tools.vision_ops.helpers.llm        — call() returns mock LLMResponse
  - tools.vision_ops.helpers.is_safe_network_address — SSRF toggle
  - tools.vision_ops.helpers.retry_sync — bypass real retry/backoff

Helpers for image content:
  - temp_image_file factory — writes fake image bytes to a tmp file
  - make_mock_response — builds a mock LLMResponse-like object
  - MockImageBlock — pre-built image_url content block (for asserting call shape)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


@pytest.fixture
def mock_cfg():
    """Patch the cfg singleton as seen by vision_ops.helpers.

    Default: vision enabled (vision_model set).
    Tests can mutate `mock.vision_model = ""` to trigger the kill-switch path.
    """
    with patch("tools.vision_ops.helpers.cfg") as mock:
        mock.vision_model = "test-vision-model"
        yield mock


@pytest.fixture
def mock_llm():
    """Patch the llm singleton as seen by vision_ops.helpers.

    Default: call() returns a mock LLMResponse (ok=True, text="OK").
    Tests can override return_value or side_effect.
    """
    with patch("tools.vision_ops.helpers.llm") as mock:
        mock_response = make_mock_response(text="OK")
        mock.call.return_value = mock_response
        yield mock


@pytest.fixture
def mock_security():
    """Patch is_safe_network_address to always return True.

    Use this for tests that exercise URL-download paths without going
    through real DNS resolution. Tests that need to assert SSRF blocking
    can override the return_value to False.
    """
    with patch("tools.vision_ops.helpers.is_safe_network_address", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_retry_sync():
    """Patch retry_sync in vision_ops.helpers to bypass real backoff sleeps.

    Default: calls the wrapped function once and returns its result.
    Tests that need to simulate retry-exhaustion can override side_effect.
    """
    from core.net.errors import is_retryable_error
    with patch("tools.vision_ops.helpers.retry_sync") as mock:
        def _passthrough(fn, **kwargs):
            return fn()
        mock.side_effect = _passthrough
        yield mock


@pytest.fixture
def temp_image_file(tmp_path):
    """Factory: write fake image bytes to a tmp file, return the path string.

    Usage:
        def test_x(temp_image_file):
            path = temp_image_file(ext=".png", data=b"\\x89PNG fake")
            result = vision(action="describe", file_path=path)

    Default: creates a fake PNG file with magic bytes.
    """
    def _make(ext: str = ".png", data: bytes = b"\x89PNG\r\n\x1a\n fake png data") -> str:
        p: Path = tmp_path / f"image{ext}"
        p.write_bytes(data)
        return str(p)
    return _make


def make_mock_response(
    *,
    ok: bool = True,
    text: str = "OK",
    model: str = "test-vision-model",
    elapsed: float = 0.5,
    usage: dict | None = None,
    parsed: object = None,
    error: str = "",
):
    """Build a mock LLMResponse-like object for llm.call.return_value."""
    mock = MagicMock()
    mock.ok = ok
    mock.text = text
    mock.model = model
    mock.elapsed = elapsed
    mock.usage = usage or {"prompt": 50, "completion": 30, "total": 80}
    mock.parsed = parsed
    mock.error = error
    return mock
