"""Tests for github issue and release actions (v1.1 + v1.2 + v1.3.1).

Covers: issue_create, issue_list, issue_comment, issue_get, issue_update,
release_create, release_list, release_get.
"""
from __future__ import annotations
import httpx
from tools.github import github


class TestIssueCreate:
    def test_issue_create_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "number": 42, "title": "Bug", "html_url": "https://github.com/test/repo/issues/42", "state": "open"
        }
        result = github(action="issue_create", title="Bug: timeout")
        assert result["status"] == "success"
        assert result["data"]["number"] == 42
        assert result["data"]["title"] == "Bug"

    def test_issue_create_not_configured(self, mock_not_configured):
        result = github(action="issue_create", title="test")
        assert result["status"] == "error"
        assert "not configured" in result["error"].lower()

    def test_issue_create_missing_title(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_create")
        assert result["status"] == "error"
        assert "title is required" in result["error"]

    def test_issue_create_with_labels(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "number": 43, "title": "Feature", "html_url": "https://github.com/test/repo/issues/43", "state": "open"
        }
        result = github(action="issue_create", title="Feature: dark mode", labels="enhancement,ui")
        assert result["status"] == "success"
        # Verify labels were passed to the API
        call_kwargs = mock_httpx_client.post.call_args
        assert call_kwargs.kwargs["json"]["labels"] == ["enhancement", "ui"]


class TestIssueList:
    def test_issue_list_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = [
            {"number": 1, "title": "Bug 1", "state": "open", "html_url": "url1", "labels": [{"name": "bug"}], "assignee": None},
            {"number": 2, "title": "Feature 1", "state": "open", "html_url": "url2", "labels": [], "assignee": {"login": "user1"}},
        ]
        result = github(action="issue_list", state="open")
        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert result["data"]["issues"][0]["number"] == 1
        assert result["data"]["issues"][1]["assignee"] == "user1"
        # v1.2 — pagination fields present
        assert result["data"]["page"] == 1
        assert result["data"]["has_next"] is False
        assert result["data"]["next_page"] is None

    def test_issue_list_not_configured(self, mock_not_configured):
        result = github(action="issue_list")
        assert result["status"] == "error"

    def test_issue_list_limit(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = [
            {"number": i, "title": f"Issue {i}", "state": "open", "html_url": f"url{i}", "labels": [], "assignee": None}
            for i in range(5)
        ]
        result = github(action="issue_list", limit=3)
        assert result["status"] == "success"
        assert result["data"]["count"] == 3

    def test_issue_list_pagination(self, mock_cfg, mock_httpx_client):
        """Link header → has_next=True, next_page=2."""
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {
            "content-type": "application/json",
            "link": '<https://api.github.com/repos/test-owner/test-repo/issues?page=2>; rel="next", <https://api.github.com/repos/test-owner/test-repo/issues?page=5>; rel="last"',
        }
        mock_httpx_client.get.return_value.json.return_value = []
        result = github(action="issue_list", page=1)
        assert result["status"] == "success"
        assert result["data"]["page"] == 1
        assert result["data"]["has_next"] is True
        assert result["data"]["next_page"] == 2


class TestIssueGet:
    def test_issue_get_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {
            "number": 42, "title": "Bug", "state": "open", "body": "Description",
            "html_url": "https://github.com/test/repo/issues/42",
            "labels": [{"name": "bug"}], "assignee": {"login": "user1"},
            "user": {"login": "devuser"},
            "created_at": "2026-07-01T10:00:00Z", "updated_at": "2026-07-02T15:00:00Z",
            "closed_at": None,
        }
        result = github(action="issue_get", number=42)
        assert result["status"] == "success"
        assert result["data"]["number"] == 42
        assert result["data"]["title"] == "Bug"
        assert result["data"]["state"] == "open"
        assert result["data"]["labels"] == ["bug"]
        assert result["data"]["assignee"] == "user1"
        assert result["data"]["user"] == "devuser"

    def test_issue_get_not_configured(self, mock_not_configured):
        result = github(action="issue_get", number=42)
        assert result["status"] == "error"
        assert "not configured" in result["error"].lower()

    def test_issue_get_missing_number(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_get")
        assert result["status"] == "error"
        assert "number is required" in result["error"]

    def test_issue_get_not_found(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 404
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {"message": "Not Found"}
        mock_httpx_client.get.return_value.text = "Not Found"
        result = github(action="issue_get", number=999)
        assert result["status"] == 404
        assert "not found" in result["error"].lower()


class TestIssueUpdate:
    def test_issue_update_close(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.patch.return_value.status_code = 200
        mock_httpx_client.patch.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.patch.return_value.json.return_value = {
            "number": 42, "title": "Bug", "state": "closed",
            "html_url": "https://github.com/test/repo/issues/42",
        }
        result = github(action="issue_update", number=42, state="closed")
        assert result["status"] == "success"
        assert result["data"]["state"] == "closed"
        # Verify PATCH was called with state=closed
        mock_httpx_client.patch.assert_called_once()
        payload = mock_httpx_client.patch.call_args.kwargs.get("json", {})
        assert payload["state"] == "closed"

    def test_issue_update_reopen(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.patch.return_value.status_code = 200
        mock_httpx_client.patch.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.patch.return_value.json.return_value = {
            "number": 42, "title": "Bug", "state": "open",
            "html_url": "https://github.com/test/repo/issues/42",
        }
        result = github(action="issue_update", number=42, state="open")
        assert result["status"] == "success"
        assert result["data"]["state"] == "open"

    def test_issue_update_edit_title_only(self, mock_cfg, mock_httpx_client):
        """state="" (default) should NOT be in the PATCH payload — only title."""
        mock_httpx_client.patch.return_value.status_code = 200
        mock_httpx_client.patch.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.patch.return_value.json.return_value = {
            "number": 42, "title": "New Title", "state": "open",
            "html_url": "https://github.com/test/repo/issues/42",
        }
        result = github(action="issue_update", number=42, title="New Title")
        assert result["status"] == "success"
        assert result["data"]["title"] == "New Title"
        # Verify state was NOT in the payload (empty = don't change)
        payload = mock_httpx_client.patch.call_args.kwargs.get("json", {})
        assert "state" not in payload
        assert payload["title"] == "New Title"

    def test_issue_update_not_configured(self, mock_not_configured):
        result = github(action="issue_update", number=42, state="closed")
        assert result["status"] == "error"
        assert "not configured" in result["error"].lower()

    def test_issue_update_missing_number(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_update", state="closed")
        assert result["status"] == "error"
        assert "number is required" in result["error"]

    def test_issue_update_no_fields(self, mock_cfg, mock_httpx_client):
        """No fields provided → fail() (at least one required)."""
        result = github(action="issue_update", number=42)
        assert result["status"] == "error"
        assert "at least one" in result["error"].lower()
        mock_httpx_client.patch.assert_not_called()

    def test_issue_update_invalid_state(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_update", number=42, state="invalid")
        assert result["status"] == "error"
        assert "state must be" in result["error"].lower()


class TestReleaseGet:
    def test_release_get_by_tag(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {
            "id": 1, "tag_name": "v1.0.0", "name": "First Release",
            "html_url": "https://github.com/test/repo/releases/tag/v1.0.0",
            "draft": False, "prerelease": False,
            "created_at": "2026-07-01T10:00:00Z", "published_at": "2026-07-02T10:00:00Z",
            "body": "## Changes\n- Initial release", "assets": [
                {"name": "app.zip", "browser_download_url": "https://github.com/test/repo/releases/download/v1.0.0/app.zip", "size": 1024, "download_count": 42},
            ],
        }
        result = github(action="release_get", tag="v1.0.0")
        assert result["status"] == "success"
        assert result["data"]["tag"] == "v1.0.0"
        assert result["data"]["name"] == "First Release"
        assert result["data"]["draft"] is False
        assert len(result["data"]["assets"]) == 1
        assert result["data"]["assets"][0]["name"] == "app.zip"
        assert result["data"]["assets"][0]["download_count"] == 42
        # Verify it used the tags endpoint
        url = mock_httpx_client.get.call_args[0][0]
        assert "/releases/tags/v1.0.0" in url

    def test_release_get_by_id(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {
            "id": 123, "tag_name": "v2.0.0", "name": "Second",
            "html_url": "url", "draft": False, "prerelease": False,
            "created_at": "", "published_at": "", "body": "", "assets": [],
        }
        result = github(action="release_get", number=123)
        assert result["status"] == "success"
        assert result["data"]["id"] == 123
        assert result["data"]["tag"] == "v2.0.0"
        # Verify it used the ID endpoint
        url = mock_httpx_client.get.call_args[0][0]
        assert "/releases/123" in url

    def test_release_get_not_configured(self, mock_not_configured):
        result = github(action="release_get", tag="v1.0.0")
        assert result["status"] == "error"
        assert "not configured" in result["error"].lower()

    def test_release_get_missing_tag_and_number(self, mock_cfg, mock_httpx_client):
        result = github(action="release_get")
        assert result["status"] == "error"
        assert "tag or number is required" in result["error"].lower()

    def test_release_get_not_found(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 404
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {"message": "Not Found"}
        mock_httpx_client.get.return_value.text = "Not Found"
        result = github(action="release_get", tag="v0.0.0")
        assert result["status"] == 404
        assert "not found" in result["error"].lower()


class TestIssueComment:
    def test_issue_comment_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "id": 12345, "html_url": "https://github.com/test/repo/issues/42#issuecomment-12345",
            "body": "Fixed in PR #45", "created_at": "2026-07-10T20:00:00Z"
        }
        result = github(action="issue_comment", number=42, body="Fixed in PR #45")
        assert result["status"] == "success"
        assert result["data"]["id"] == 12345

    def test_issue_comment_missing_number(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_comment", body="test")
        assert result["status"] == "error"
        assert "number is required" in result["error"]

    def test_issue_comment_missing_body(self, mock_cfg, mock_httpx_client):
        result = github(action="issue_comment", number=42)
        assert result["status"] == "error"
        assert "body is required" in result["error"]

    def test_issue_comment_coerces_string_number(self, mock_cfg, mock_httpx_client):
        """v1.3.1 (P3-2 cross-LLM): issue_comment now coerces number to int
        for parity with issue_get/issue_update/pr_get/pr_review/pr_merge/pr_comment.
        v1.1 used number directly in the URL (worked by luck for numeric strings).
        """
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "id": 1, "html_url": "url", "body": "test", "created_at": "2026-07-10"
        }
        result = github(action="issue_comment", number="42", body="test")
        assert result["status"] == "success"
        # Verify the URL used the int-coerced number
        call_args = mock_httpx_client.post.call_args
        assert "/issues/42/comments" in call_args[0][0]

    def test_issue_comment_rejects_non_numeric_number(self, mock_cfg, mock_httpx_client):
        """v1.3.1 (P3-2): non-numeric number now fails fast instead of hitting the API."""
        result = github(action="issue_comment", number="abc", body="test")
        assert result["status"] == "error"
        assert "must be an int" in result["error"]


class TestReleaseCreate:
    def test_release_create_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "id": 1, "tag_name": "v1.0.0", "name": "First Release",
            "html_url": "https://github.com/test/repo/releases/tag/v1.0.0",
            "draft": False, "prerelease": False, "created_at": "2026-07-10T20:00:00Z"
        }
        result = github(action="release_create", tag="v1.0.0", title="First Release")
        assert result["status"] == "success"
        assert result["data"]["tag"] == "v1.0.0"

    def test_release_create_missing_tag(self, mock_cfg, mock_httpx_client):
        result = github(action="release_create", title="test")
        assert result["status"] == "error"
        assert "tag is required" in result["error"]

    def test_release_create_prerelease(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 201
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {
            "id": 2, "tag_name": "v2.0.0-beta", "name": "Beta",
            "html_url": "url", "draft": False, "prerelease": True, "created_at": "2026-07-10T20:00:00Z"
        }
        result = github(action="release_create", tag="v2.0.0-beta", title="Beta", prerelease=True)
        assert result["status"] == "success"
        assert result["data"]["prerelease"] is True


class TestReleaseList:
    def test_release_list_success(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = [
            {"id": 2, "tag_name": "v1.1.0", "name": "Second", "html_url": "url2", "draft": False, "prerelease": False, "published_at": "2026-07-09"},
            {"id": 1, "tag_name": "v1.0.0", "name": "First", "html_url": "url1", "draft": False, "prerelease": False, "published_at": "2026-07-08"},
        ]
        result = github(action="release_list")
        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert result["data"]["releases"][0]["tag"] == "v1.1.0"

    def test_release_list_not_configured(self, mock_not_configured):
        result = github(action="release_list")
        assert result["status"] == "error"

    def test_release_list_limit(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = [
            {"id": i, "tag_name": f"v{i}.0.0", "name": f"Release {i}", "html_url": f"url{i}", "draft": False, "prerelease": False, "published_at": "2026-07-08"}
            for i in range(5)
        ]
        result = github(action="release_list", limit=2)
        assert result["status"] == "success"
        assert result["data"]["count"] == 2

    def test_release_list_pagination(self, mock_cfg, mock_httpx_client):
        """v1.3.1 (P2-2 cross-LLM): release_list now supports pagination
        (page param + has_next/next_page from Link header), matching pr_list
        and issue_list. v1.1 was capped at 100 items with no pagination.
        """
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.headers = {
            "content-type": "application/json",
            "link": '<https://api.github.com/repos/test/test/releases?page=2>; rel="next", <https://api.github.com/repos/test/test/releases?page=3>; rel="last"',
        }
        mock_httpx_client.get.return_value.json.return_value = [
            {"id": 1, "tag_name": "v1.0.0", "name": "First", "html_url": "url1", "draft": False, "prerelease": False, "published_at": "2026-07-08"}
        ]
        result = github(action="release_list", page=1)
        assert result["status"] == "success"
        assert result["data"]["page"] == 1
        assert result["data"]["has_next"] is True
        assert result["data"]["next_page"] == 2


class TestV131ErrorHandling:
    """v1.3.1 (P2-1 cross-LLM): v1.1 actions now use the v1.0/v1.2 3-stage
    error-handling pattern — network call → HTTP error → JSON parse, with
    status= and trace_id= on all fail()/ok() calls.
    """

    def test_issue_create_api_error_has_status_code(self, mock_cfg, mock_httpx_client):
        """v1.1 bug: fail() had no status= kwarg — callers couldn't distinguish
        404 from 422 from 500. v1.3.1 propagates status_code via fail(status=...).
        """
        mock_httpx_client.post.return_value.status_code = 422
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {"message": "Validation failed"}
        mock_httpx_client.post.return_value.text = '{"message": "Validation failed"}'
        result = github(action="issue_create", title="test")
        assert result["status"] == 422  # HTTP code propagated (convention: status= is the int)
        assert "422" in result["error"]
        assert "Validation failed" in result["error"]

    def test_release_create_api_error_has_status_code(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.post.return_value.status_code = 403
        mock_httpx_client.post.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.post.return_value.json.return_value = {"message": "Forbidden"}
        mock_httpx_client.post.return_value.text = '{"message": "Forbidden"}'
        result = github(action="release_create", tag="v1.0.0")
        assert result["status"] == 403
        assert "403" in result["error"]

    def test_release_list_api_error_has_status_code(self, mock_cfg, mock_httpx_client):
        mock_httpx_client.get.return_value.status_code = 500
        mock_httpx_client.get.return_value.headers = {"content-type": "application/json"}
        mock_httpx_client.get.return_value.json.return_value = {"message": "Server error"}
        mock_httpx_client.get.return_value.text = '{"message": "Server error"}'
        result = github(action="release_list")
        assert result["status"] == 500
        assert "500" in result["error"]

    def test_issue_comment_network_error_distinct_from_parse_error(self, mock_cfg, mock_httpx_client):
        """v1.1 bug: single try/except caught both network errors AND JSON parse
        errors as 'issue_comment failed: {e}'. v1.3.1 distinguishes them.
        """
        # Network error (request raises)
        mock_httpx_client.post.side_effect = httpx.ConnectError("connection refused")
        result = github(action="issue_comment", number=42, body="test")
        assert result["status"] == "error"
        assert "request failed" in result["error"]  # network, not parse
