"""Shared fixtures for github tool tests.

All GitHub infrastructure is fully mocked — no real httpx calls to the GitHub
API and no real `git push` subprocess. The fixtures here follow the same
pattern as `tests/tools/tavily/conftest.py` (mock client singleton) and
`tests/tools/swarm/conftest.py` (mock registry).

IMPORTANT — get_client patching strategy:
  Each action module imports `get_client` by name from `tools.github_ops.client`
  (`from tools.github_ops.client import get_client`). After import, the action
  module holds a direct reference to the function object — patching
  `tools.github_ops.client.get_client` AFTER import does NOT intercept calls
  made via the action module's local reference.

  The fix is to patch `get_client` at every action module's namespace
  (`tools.github_ops.actions.<name>.get_client`). The `mock_httpx_client`
  fixture below patches all 6 API-based action modules. (`push` doesn't need
  patching — it uses subprocess directly, no httpx.)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# All github_ops action modules that import get_client from client.py.
# push.py is intentionally NOT in this list — it uses subprocess, not httpx.
_API_ACTION_MODULES = (
    "pr_create",
    "pr_list",
    "pr_get",
    "pr_review",
    "pr_merge",
    "pr_comment",
)


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
    """Mock the github_ops httpx.Client for all 6 API-based action modules.

    Patches `get_client` in each action module's namespace so calls like
    `client.post(...)` / `client.get(...)` / `client.put(...)` hit the
    MagicMock instead of making real HTTP calls to api.github.com.

    Tests can override `mock_client.post.return_value` / `.get.return_value` /
    `.put.return_value` with canned responses built via `_make_response()`.

    The mock_cfg fixture is included as a dependency so is_configured()
    returns True — without it, the action handler short-circuits before
    ever calling get_client().
    """
    mock_client = MagicMock()
    # Default: 200 OK with empty JSON body — individual tests override
    # .get/.post/.put return_value as needed.
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}
    mock_response.text = ""
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client.put.return_value = mock_response

    patches = [
        patch(f"tools.github_ops.actions.{m}.get_client", return_value=mock_client)
        for m in _API_ACTION_MODULES
    ]
    for p in patches:
        p.start()

    try:
        yield mock_client
    finally:
        for p in patches:
            p.stop()


def _make_response(status_code: int = 200, json_body: dict | None = None,
                   text: str = "") -> MagicMock:
    """Helper to build a mock httpx.Response with a specific status + body.

    Tests can use this to construct canned API responses:
        mock_client.post.return_value = _make_response(201, {"number": 42, ...})
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp
