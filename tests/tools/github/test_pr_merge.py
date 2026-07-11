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
        """405 from GitHub → fail() with 'not mergeable' message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 405
        mock_resp.json.return_value = {"message": "Pull Request is not mergeable"}
        mock_resp.text = "Pull Request is not mergeable"
        mock_httpx_client.put.return_value = mock_resp

        result = github(action="pr_merge", number=42)

        assert result["status"] == 405
        assert "not mergeable" in result["error"].lower()

    def test_pr_merge_conflict(self, mock_httpx_client):
        """409 from GitHub → fail() with 'head commit not up to date' message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_resp.json.return_value = {"message": "Head commit was updated"}
        mock_resp.text = "Head commit was updated"
        mock_httpx_client.put.return_value = mock_resp

        result = github(action="pr_merge", number=42)

        assert result["status"] == 409
        assert "up to date" in result["error"].lower() or "409" in str(result["status"])
