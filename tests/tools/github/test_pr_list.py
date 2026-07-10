"""Tests for github pr_list action.

Covers: success path, "not configured" error, state filter pass-through.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key:
  ok({"count": 2, "pulls": [...]}) -> {"status": "success", "data": {...}, "error": None}
So success assertions check `result["data"]["count"]`, etc.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_pr_list_response(prs: list[dict]) -> MagicMock:
    """Build a mock GitHub API response for GET /repos/.../pulls."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = prs
    resp.text = ""
    return resp


class TestPrList:
    """pr_list fetches pull requests filtered by state from the GitHub API."""

    def test_pr_list_success(self, mock_httpx_client):
        """Mock returns 2 PRs — facade should normalize and return count + list."""
        mock_httpx_client.get.return_value = _make_pr_list_response([
            {
                "number": 42, "title": "Fix timeout bug", "state": "open",
                "head": {"ref": "fix/timeout"}, "base": {"ref": "main"},
                "html_url": "https://github.com/test-owner/test-repo/pull/42",
                "draft": False,
            },
            {
                "number": 41, "title": "Add login page", "state": "open",
                "head": {"ref": "feat/login"}, "base": {"ref": "main"},
                "html_url": "https://github.com/test-owner/test-repo/pull/41",
                "draft": True,
            },
        ])

        result = github(action="pr_list")

        assert result["status"] == "success"
        data = result["data"]
        assert data["count"] == 2
        assert len(data["pulls"]) == 2
        # First PR — non-draft
        pr0 = data["pulls"][0]
        assert pr0["number"] == 42
        assert pr0["title"] == "Fix timeout bug"
        assert pr0["state"] == "open"
        assert pr0["head"] == "fix/timeout"
        assert pr0["base"] == "main"
        assert pr0["draft"] is False
        # Second PR — draft
        pr1 = data["pulls"][1]
        assert pr1["number"] == 41
        assert pr1["draft"] is True
        assert "duration_ms" in result

    def test_pr_list_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(action="pr_list")

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]
        assert "GITHUB_TOKEN" in result["error"]

    def test_pr_list_state_filter(self, mock_httpx_client):
        """state=closed should be passed through as a query param to the API."""
        mock_httpx_client.get.return_value = _make_pr_list_response([])

        result = github(action="pr_list", state="closed", limit=15)

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

        # Verify state and per_page were forwarded as query params
        mock_httpx_client.get.assert_called_once()
        call_kwargs = mock_httpx_client.get.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("state") == "closed"
        # per_page is capped at min(limit, 100)
        assert params.get("per_page") == 15
