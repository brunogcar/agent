"""Tests for github issue_create action."""
from __future__ import annotations
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
