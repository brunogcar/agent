"""Tests for github pr_review action.

Covers: success (APPROVE / REQUEST_CHANGES / COMMENT), "not configured",
missing number, missing event, invalid event.

NOTE: `ok()` from core.contracts wraps data under the top-level `data` key.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.github import github


def _make_review_response(review_id: int = 12345, state: str = "APPROVED") -> MagicMock:
    """Build a mock GitHub API response for POST /repos/.../pulls/{n}/reviews."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "id": review_id,
        "state": state,
        "html_url": f"https://github.com/test-owner/test-repo/pull/42#review-{review_id}",
    }
    resp.text = ""
    return resp


class TestPrReview:
    """pr_review submits a review (APPROVE / REQUEST_CHANGES / COMMENT) on a PR."""

    def test_pr_review_approve(self, mock_httpx_client):
        """APPROVE event → ok() with review id + state."""
        mock_httpx_client.post.return_value = _make_review_response(
            review_id=12345, state="APPROVED"
        )

        result = github(action="pr_review", number=42, event="APPROVE", body="LGTM")

        assert result["status"] == "success"
        data = result["data"]
        assert data["id"] == 12345
        assert data["state"] == "APPROVED"
        assert "duration_ms" in result

        # Verify payload
        mock_httpx_client.post.assert_called_once()
        payload = mock_httpx_client.post.call_args[1].get("json", {})
        assert payload["event"] == "APPROVE"
        assert payload["body"] == "LGTM"

    def test_pr_review_request_changes(self, mock_httpx_client):
        """REQUEST_CHANGES event → ok() with PENDING state."""
        mock_httpx_client.post.return_value = _make_review_response(
            review_id=12346, state="CHANGES_REQUESTED"
        )

        result = github(
            action="pr_review", number=42, event="REQUEST_CHANGES",
            body="Needs null check on line 17"
        )

        assert result["status"] == "success"
        assert result["data"]["state"] == "CHANGES_REQUESTED"

    def test_pr_review_comment(self, mock_httpx_client):
        """COMMENT event → ok() with COMMENTED state."""
        mock_httpx_client.post.return_value = _make_review_response(
            review_id=12347, state="COMMENTED"
        )

        result = github(action="pr_review", number=42, event="COMMENT", body="Just a note")

        assert result["status"] == "success"
        assert result["data"]["state"] == "COMMENTED"

    def test_pr_review_not_configured(self, mock_not_configured):
        """No token configured → fail() with the env-var hint message."""
        result = github(action="pr_review", number=42, event="APPROVE")

        assert result["status"] == "error"
        assert "GitHub not configured" in result["error"]

    def test_pr_review_missing_number(self, mock_httpx_client):
        """Missing number → fail() (validated before any API call)."""
        result = github(action="pr_review", event="APPROVE")

        assert result["status"] == "error"
        assert "number is required" in result["error"]
        mock_httpx_client.post.assert_not_called()

    def test_pr_review_missing_event(self, mock_httpx_client):
        """Missing event → fail() (validated before any API call)."""
        result = github(action="pr_review", number=42)

        assert result["status"] == "error"
        assert "event is required" in result["error"]
        mock_httpx_client.post.assert_not_called()

    def test_pr_review_invalid_event(self, mock_httpx_client):
        """Invalid event → fail() listing valid events."""
        result = github(action="pr_review", number=42, event="INVALID")

        assert result["status"] == "error"
        assert "APPROVE" in result["error"]
        assert "REQUEST_CHANGES" in result["error"]
        assert "COMMENT" in result["error"]
