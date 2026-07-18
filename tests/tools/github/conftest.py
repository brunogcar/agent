"""Shared fixtures for github tool tests.

All GitHub infrastructure is fully mocked — no real httpx calls to the GitHub
API and no real `git push` subprocess. The fixtures here follow the same
pattern as `tests/tools/tavily/conftest.py` (mock client singleton) and
`tests/tools/swarm/conftest.py` (mock registry).

IMPORTANT — get_client patching strategy (v1.5):
  v1.4 and earlier: each action module imported `get_client` by name from
  `tools.github_ops.client` and held a direct reference. Tests patched
  `tools.github_ops.actions.<module>.get_client` for all 14 modules.

  v1.5: action modules no longer import `get_client` directly. They call
  `github_request()` (from `tools.github_ops.helpers`), which calls
  `get_client()` internally. The single patch target is now
  `tools.github_ops.helpers.get_client` — one patch covers all 14 actions.

  `push` and `pull` don't need patching — they use subprocess, not httpx.

v1.5 retry handling:
  `github_request()` wraps the httpx call in `core.net.retry.retry_sync`
  (max_retries=2, base_delay=1.0). For tests that mock 500/ConnectError
  responses (both retryable), this would cause real `time.sleep` calls
  (~3-5s per test). To keep tests fast, the `mock_httpx_client` fixture
  also patches `core.net.retry._sleep` to a no-op for the duration of
  the test. (v1.6 of retry.py specifically introduced the module-level
  `_sleep` reference so tests can patch it without globally mocking
  `time.sleep`.)
"""
from __future__ import annotations

import httpx
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_cfg():
    """Patch core.config.cfg with github_token, github_owner, github_repo.

    Makes `is_configured()` return True for the duration of the test.
    Patches at the source attribute level so every module that reads
    `cfg.github_token` / `cfg.github_owner` / `cfg.github_repo` sees the
    test values.
    """
    with patch("core.config.cfg.github_token", "ghp_test_token_abc123"):
        with patch("core.config.cfg.github_owner", "test-owner"):
            with patch("core.config.cfg.github_repo", "test-repo"):
                yield


@pytest.fixture
def mock_not_configured():
    """Patch core.config.cfg with EMPTY github_token.

    Makes `is_configured()` return False — used for "not configured" error
    paths. Only `github_token` is set to empty; the other two are left
    as-is because `is_configured()` short-circuits on the first empty value.
    """
    with patch("core.config.cfg.github_token", ""):
        yield


@pytest.fixture
def mock_httpx_client(mock_cfg):
    """Mock the github_ops httpx.Client for all 14 API-based action modules.

    v1.5: Patches `get_client` at `tools.github_ops.helpers.get_client` —
    the single namespace where github_request() looks it up. This covers
    all 14 migrated action modules (issue_*, pr_*, release_*) because
    they all go through `github_request()`.

    Tests can override `mock_client.post.return_value` / `.get.return_value` /
    `.put.return_value` with canned responses built via `_make_response()`.

    The mock_cfg fixture is included as a dependency so is_configured()
    returns True — without it, the action handler short-circuits before
    ever calling get_client().

    Also patches `core.net.retry._sleep` to a no-op so tests that mock
    retryable responses (500, ConnectError, etc.) don't pay the real
    backoff sleep (~1-5s per retry).
    """
    mock_client = MagicMock()
    # Default: 200 OK with empty JSON body — individual tests override
    # .get/.post/.put return_value as needed.
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}
    mock_response.text = ""
    mock_response.headers = {}

    # v1.5: github_request()'s _do_request helper calls `resp.raise_for_status()`
    # when `resp.status_code >= 400`. The mock's raise_for_status() is a no-op
    # MagicMock by default, so 4xx/5xx responses silently passed through as
    # success. Configure raise_for_status to raise a real httpx.HTTPStatusError
    # bound to this mock_response whenever status_code >= 400. Tests that mutate
    # `mock_client.<method>.return_value.status_code = 4xx` after the fixture
    # runs still get the correct behavior because the side_effect reads the
    # current status_code at call time.
    def _raise_for_status(*_args, **_kwargs):
        if mock_response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {mock_response.status_code}",
                request=httpx.Request("GET", "https://api.github.com"),
                response=mock_response,
            )

    mock_response.raise_for_status.side_effect = _raise_for_status

    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client.put.return_value = mock_response

    patches = [
        # v1.5: single patch target — helpers.get_client.
        patch("tools.github_ops.helpers.get_client", return_value=mock_client),
        # v1.5: no-op _sleep so retry backoff doesn't slow tests.
        patch("core.net.retry._sleep", lambda *_args, **_kwargs: None),
    ]
    for p in patches:
        p.start()

    try:
        yield mock_client
    finally:
        for p in patches:
            p.stop()


def _make_response(status_code: int = 200, json_body: dict | None = None,
                   text: str = "", headers: dict | None = None) -> MagicMock:
    """Helper to build a mock httpx.Response with a specific status + body.

    Tests can use this to construct canned API responses:
        mock_client.post.return_value = _make_response(201, {"number": 42, ...})

    v1.3.1 (P3-3 cross-LLM): Added `headers` param (defaults to empty dict).
    Previously, _make_response() didn't set .headers, so resp.headers.get("link", "")
    returned a MagicMock instead of a string — breaking pagination tests that used
    _make_response() for pr_list/issue_list. Now .headers is always a real dict.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    resp.headers = headers if headers is not None else {}
    return resp
