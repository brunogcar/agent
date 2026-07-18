"""Tests for github pr_merge action.

Covers: success (squash/merge/rebase), "not configured", missing number,
invalid merge_method, 405 not mergeable, 409 conflict.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_merge_response(sha: str = "abc123def456") -> MagicMock:
    """Build a mock GitHub API response for PUT /repos/.../pulls/{n}/merge."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "sha": sha,
        "merged": True,
        "message": "Pull Request successfully merged",
    }
    resp.text = ""
    return resp


class TestPrMerge:
    """pr_merge merges a pull request via the GitHub API."""

    def test_pr_merge_squash(self, mock_httpx_client):
        """Default squash merge → ok() with sha + merged=True."""
        mock_httpx_client.put.return_value = _make_merge_response(sha="abc123")

        result = github(action="pr_merge", number=42)

        assert result["status"] == "success"
        data = result["data"]
        assert data["merged"] is True
        assert data["sha"] == "abc123"
        assert "duration_ms" in result

        # Verify default merge_method is squash
        mock_httpx_client.put.assert_called_once()
        payload = mock_httpx_client.put.call_args[1].get("json", {})
        assert payload["merge_method"] == "squash"

    def test_pr_merge_with_custom_method(self, mock_httpx_client):
        """merge_method=merge → passes through to API."""
        mock_httpx_client.put.return_value = _make_merge_response(sha="def456")

        result = github(
            action="pr_merge", number=42,
            merge_method="merge", commit_title="Merge PR #42"
        )

        assert result["status"] == "success"
        payload = mock_httpx_client.put.call_args[1].get("json", {})
        assert payload["merge_method"] == "merge"
        assert payload["commit_title"] == "Merge PR #42"

    def test_pr_merge_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(action="pr_merge", number=42)

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]

    def test_pr_merge_missing_number(self, mock_httpx_client):
        """Missing number → fail() (validated before any API call)."""
        result = github(action="pr_merge")

        assert result["status"] == "error"
        assert "number is required" in result["error"]
        mock_httpx_client.put.assert_not_called()

    def test_pr_merge_invalid_method(self, mock_httpx_client):
        """Invalid merge_method → fail() listing valid methods."""
        result = github(action="pr_merge", number=42, merge_method="invalid")

        assert result["status"] == "error"
        assert "merge" in result["error"]
        assert "squash" in result["error"]
        assert "rebase" in result["error"]
        mock_httpx_client.put.assert_not_called()

    def test_pr_merge_not_mergeable(self, mock_httpx_client):
        """405 from GitHub → fail() with 'not mergeable' message.

        v1.5: 405 now goes through github_request()'s generic >=400 branch,
        which returns "GitHub API error 405: <gh_msg>". The mock's gh_msg
        is "Pull Request is not mergeable" — so the "not mergeable"
        substring is still present (sourced from GitHub's own message).
        """
        # Mutate the default mock_response (which has raise_for_status.side_effect
        # configured by the conftest fixture).
        mock_httpx_client.put.return_value.status_code = 405
        mock_httpx_client.put.return_value.json.return_value = {"message": "Pull Request is not mergeable"}
        mock_httpx_client.put.return_value.text = "Pull Request is not mergeable"
        mock_httpx_client.put.return_value.headers = {}

        result = github(action="pr_merge", number=42)

        assert result["status"] == "error"
        assert "not mergeable" in result["error"].lower()

    def test_pr_merge_conflict(self, mock_httpx_client):
        """409 from GitHub → fail() with the GitHub API error message.

        v1.5 BEHAVIOR CHANGE: the v1.4 inline pattern had a custom 409
        message ("head commit is not up to date — rebase and push again").
        With github_request(), 409 now falls through to the generic
        "GitHub API error 409: <gh_msg>" branch — the HTTP code is still
        in the message and GitHub's own message string is preserved, but
        the friendly "up to date" phrasing is gone.
        """
        mock_httpx_client.put.return_value.status_code = 409
        mock_httpx_client.put.return_value.json.return_value = {"message": "Head commit was updated"}
        mock_httpx_client.put.return_value.text = "Head commit was updated"
        mock_httpx_client.put.return_value.headers = {}

        result = github(action="pr_merge", number=42)

        assert result["status"] == "error"
        assert "409" in result["error"]
        assert "Head commit was updated" in result["error"]
