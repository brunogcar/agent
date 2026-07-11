"""Tests for github pr_comment action.

Covers: general comment, line-level comment, "not configured", missing
number, missing body, path/line mismatch (one without the other).

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_comment_response(comment_id: int = 99, body: str = "Nice work") -> MagicMock:
    """Build a mock GitHub API response for POST comment endpoints."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {
        "id": comment_id,
        "html_url": f"https://github.com/test-owner/test-repo/pull/42#issuecomment-{comment_id}",
        "body": body,
    }
    resp.text = ""
    return resp


def _make_line_comment_response(comment_id: int = 100) -> MagicMock:
    """Build a mock GitHub API response for line-level PR comments."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {
        "id": comment_id,
        "html_url": f"https://github.com/test-owner/test-repo/pull/42#discussion_r{comment_id}",
        "body": "Missing null check",
        "path": "src/main.py",
        "line": 42,
    }
    resp.text = ""
    return resp


class TestPrComment:
    """pr_comment posts a general or line-level comment on a pull request."""

    def test_pr_comment_general(self, mock_httpx_client):
        """General comment (no path/line) → ok() with id, url, body."""
        mock_httpx_client.post.return_value = _make_comment_response(
            comment_id=99, body="This needs a null check"
        )

        result = github(action="pr_comment", number=42, body="This needs a null check")

        assert result["status"] == "success"
        data = result["data"]
        assert data["id"] == 99
        assert data["body"] == "This needs a null check"
        assert "path" not in data  # general comment, no path
        assert "duration_ms" in result

        # Verify it used the issues/{number}/comments endpoint (general)
        mock_httpx_client.post.assert_called_once()
        url = mock_httpx_client.post.call_args[0][0]
        assert "/issues/42/comments" in url

    def test_pr_comment_line_level(self, mock_httpx_client):
        """Line-level comment (path + line) → ok() with path + line in result."""
        mock_httpx_client.post.return_value = _make_line_comment_response(comment_id=100)

        result = github(
            action="pr_comment", number=42, body="Missing null check",
            path="src/main.py", line=42
        )

        assert result["status"] == "success"
        data = result["data"]
        assert data["id"] == 100
        assert data["path"] == "src/main.py"
        assert data["line"] == 42

        # Verify it used the pulls/{number}/comments endpoint (line-level)
        url = mock_httpx_client.post.call_args[0][0]
        assert "/pulls/42/comments" in url

        # Verify payload includes path, line, side, subject_type
        payload = mock_httpx_client.post.call_args[1].get("json", {})
        assert payload["path"] == "src/main.py"
        assert payload["line"] == 42
        assert payload["side"] == "RIGHT"
        assert payload["subject_type"] == "line"

    def test_pr_comment_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(action="pr_comment", number=42, body="test")

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]

    def test_pr_comment_missing_number(self, mock_httpx_client):
        """Missing number → fail() (validated before any API call)."""
        result = github(action="pr_comment", body="test")

        assert result["status"] == "error"
        assert "number is required" in result["error"]
        mock_httpx_client.post.assert_not_called()

    def test_pr_comment_missing_body(self, mock_httpx_client):
        """Missing body → fail() (validated before any API call)."""
        result = github(action="pr_comment", number=42)

        assert result["status"] == "error"
        assert "body is required" in result["error"]
        mock_httpx_client.post.assert_not_called()

    def test_pr_comment_path_without_line(self, mock_httpx_client):
        """Path without line → fail() (both required for line-level)."""
        result = github(
            action="pr_comment", number=42, body="test", path="src/main.py"
        )

        assert result["status"] == "error"
        assert "path and line must be provided together" in result["error"]
        mock_httpx_client.post.assert_not_called()

    def test_pr_comment_line_without_path(self, mock_httpx_client):
        """Line without path → fail() (both required for line-level)."""
        result = github(action="pr_comment", number=42, body="test", line=42)

        assert result["status"] == "error"
        assert "path and line must be provided together" in result["error"]
        mock_httpx_client.post.assert_not_called()
