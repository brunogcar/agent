"""Tests for github pr_get action.

Covers: success path (with mergeable states), "not configured" error,
missing number, 404 not found, non-numeric number.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key:
  ok({...}) -> {"status": "success", "data": {...}, "error": None}
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_pr_get_response(
    number: int = 42,
    title: str = "Fix timeout bug",
    state: str = "open",
    merged: bool = False,
    mergeable: bool | None = True,
    mergeable_state: str = "clean",
    draft: bool = False,
) -> MagicMock:
    """Build a mock GitHub API response for GET /repos/.../pulls/{number}."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "number": number,
        "title": title,
        "state": state,
        "merged": merged,
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "draft": draft,
        "head": {"ref": "fix/timeout"},
        "base": {"ref": "main"},
        "html_url": f"https://github.com/test-owner/test-repo/pull/{number}",
        "body": "Fixes the intermittent timeout.",
        "user": {"login": "devuser"},
        "created_at": "2026-07-01T10:00:00Z",
        "updated_at": "2026-07-02T15:00:00Z",
    }
    resp.text = ""
    return resp


class TestPrGet:
    """pr_get fetches a single pull request's details from the GitHub API."""

    def test_pr_get_success(self, mock_httpx_client):
        """Mock returns PR data — facade should return ok() with all fields."""
        mock_httpx_client.get.return_value = _make_pr_get_response(
            number=42, mergeable=True, mergeable_state="clean"
        )

        result = github(action="pr_get", number=42)

        assert result["status"] == "success"
        data = result["data"]
        assert data["number"] == 42
        assert data["title"] == "Fix timeout bug"
        assert data["state"] == "open"
        assert data["merged"] is False
        assert data["mergeable"] is True
        assert data["mergeable_state"] == "clean"
        assert data["draft"] is False
        assert data["head"] == "fix/timeout"
        assert data["base"] == "main"
        assert data["user"] == "devuser"
        assert "duration_ms" in result

        # Verify the API call URL
        mock_httpx_client.get.assert_called_once()
        url = mock_httpx_client.get.call_args[0][0]
        assert "/repos/test-owner/test-repo/pulls/42" in url

    def test_pr_get_mergeable_null(self, mock_httpx_client):
        """mergeable=null means GitHub is still computing — should pass through."""
        mock_httpx_client.get.return_value = _make_pr_get_response(
            mergeable=None, mergeable_state="unknown"
        )

        result = github(action="pr_get", number=42)

        assert result["status"] == "success"
        assert result["data"]["mergeable"] is None
        assert result["data"]["mergeable_state"] == "unknown"

    def test_pr_get_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(action="pr_get", number=42)

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]

    def test_pr_get_missing_number(self, mock_httpx_client):
        """Missing number → fail() (validated before any API call)."""
        result = github(action="pr_get")

        assert result["status"] == "error"
        assert "number is required" in result["error"]
        # No API call should have been made
        mock_httpx_client.get.assert_not_called()

    def test_pr_get_not_found(self, mock_httpx_client):
        """404 from GitHub → fail() with 'not found' message.

        v1.5: 404 now goes through github_request()'s not_found_msg branch,
        which returns the friendly "PR #<n> not found" message (set by the
        action) instead of the generic "GitHub API error 404: ...".
        """
        # Mutate the default mock_response (which has raise_for_status.side_effect
        # configured by the conftest fixture) rather than building a fresh
        # MagicMock that would silently no-op on raise_for_status().
        mock_httpx_client.get.return_value.status_code = 404
        mock_httpx_client.get.return_value.json.return_value = {"message": "Not Found"}
        mock_httpx_client.get.return_value.text = "Not Found"
        mock_httpx_client.get.return_value.headers = {}

        result = github(action="pr_get", number=999)

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    def test_pr_get_non_numeric_number(self, mock_httpx_client):
        """Non-numeric number → fail() with type error."""
        result = github(action="pr_get", number="abc")

        assert result["status"] == "error"
        assert "number must be an int" in result["error"]
