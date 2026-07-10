"""Tests for github pr_create action.

Covers: success path, "not configured" error, missing title, missing head.
All tests mock the httpx client to avoid real GitHub API calls.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key:
  ok({"number": 42, "title": "..."}) -> {"status": "success", "data": {...}, "error": None}
So success assertions check `result["data"]["number"]`, etc.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_pr_response(number: int = 42, title: str = "Fix timeout bug",
                      head: str = "fix/timeout", base: str = "main") -> MagicMock:
    """Build a mock GitHub API response for POST /repos/.../pulls."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/test-owner/test-repo/pull/{number}",
        "state": "open",
        "head": {"ref": head},
        "base": {"ref": base},
    }
    resp.text = ""
    return resp


class TestPrCreate:
    """pr_create opens a new pull request via the GitHub API."""

    def test_pr_create_success(self, mock_httpx_client):
        """Mock returns PR data — facade should return ok() with normalized fields."""
        mock_httpx_client.post.return_value = _make_pr_response(
            number=42, title="Fix timeout bug", head="fix/timeout", base="main"
        )

        result = github(
            action="pr_create",
            title="Fix timeout bug",
            head="fix/timeout",
            base="main",
            body="Resolves intermittent timeouts in the search retry loop.",
        )

        assert result["status"] == "success"
        # ok() nests the action's payload under result["data"]
        data = result["data"]
        assert data["number"] == 42
        assert data["title"] == "Fix timeout bug"
        assert data["url"] == "https://github.com/test-owner/test-repo/pull/42"
        assert data["state"] == "open"
        assert data["head"] == "fix/timeout"
        assert data["base"] == "main"
        assert "duration_ms" in result

        # Verify the API call was made with the right URL + payload
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "/repos/test-owner/test-repo/pulls" in url
        payload = call_args[1].get("json", {})
        assert payload["title"] == "Fix timeout bug"
        assert payload["head"] == "fix/timeout"
        assert payload["base"] == "main"
        assert payload["body"].startswith("Resolves intermittent")

    def test_pr_create_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(
            action="pr_create",
            title="Fix timeout bug",
            head="fix/timeout",
        )

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]
        assert "GITHUB_TOKEN" in result["error"]
        assert "GITHUB_OWNER" in result["error"]
        assert "GITHUB_REPO" in result["error"]

    def test_pr_create_missing_title(self, mock_httpx_client):
        """Missing title → fail() (validated before any API call)."""
        result = github(
            action="pr_create",
            title="",
            head="fix/timeout",
        )

        assert result["status"] == "error"
        assert "title is required" in result["error"]
        # No API call should have been made
        mock_httpx_client.post.assert_not_called()

    def test_pr_create_missing_head(self, mock_httpx_client):
        """Missing head (source branch) → fail() (validated before any API call)."""
        result = github(
            action="pr_create",
            title="Fix timeout bug",
            head="",
        )

        assert result["status"] == "error"
        assert "head" in result["error"]
        assert "required" in result["error"]
        # No API call should have been made
        mock_httpx_client.post.assert_not_called()
