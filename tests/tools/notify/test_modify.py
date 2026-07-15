"""Tests for notify modify action — update existing job's metadata. [NEW]

Covers:
  1. Success path (title + message both updated)
  2. Missing job_id → error
  3. Job not found → error
  4. Partial update (only title, or only message)
  5. No-op update (both title and message empty) → error
  6. trace_id threading
  7. _save_jobs called
"""
from __future__ import annotations

from unittest.mock import patch

from tools.notify import notify
from tools.notify_ops import state


def _seed_job(job_id: str = "job_mod_1", title: str = "Old Title", message: str = "Old Message") -> None:
    """Helper: seed the in-memory registry with a fake scheduled job."""
    state._job_registry[job_id] = {
        "title": title,
        "message": message,
        "run_at": "2099-01-01T00:00:00",
        "cron": "",
        "status": "scheduled",
        "recurring": False,
    }


class TestModifySuccess:
    """modify: successful metadata update."""

    def test_modify_updates_title_and_message(self, mock_cfg, mock_scheduler):
        """Should update both title and message when both provided."""
        _seed_job()
        result = notify(action="modify", job_id="job_mod_1",
                        title="New Title", message="New Message")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "modified"
        assert result["data"]["action"] == "modify"
        assert result["data"]["job_id"] == "job_mod_1"
        assert "title" in result["data"]["updated_fields"]
        assert "message" in result["data"]["updated_fields"]
        # Verify the registry was actually updated.
        assert state._job_registry["job_mod_1"]["title"] == "New Title"
        assert state._job_registry["job_mod_1"]["message"] == "New Message"

    def test_modify_save_jobs_called(self, mock_cfg, mock_scheduler):
        """_save_jobs should be called after the registry update."""
        _seed_job()
        with patch("tools.notify_ops.state._save_jobs") as mock_save:
            notify(action="modify", job_id="job_mod_1", title="New")
        mock_save.assert_called_once()


class TestModifyPartialUpdate:
    """modify: partial updates (only title OR only message)."""

    def test_modify_only_title(self, mock_cfg, mock_scheduler):
        """Updating only title should leave message unchanged."""
        _seed_job(title="Old Title", message="Keep Me")
        result = notify(action="modify", job_id="job_mod_1",
                        title="New Title", message="")
        assert result["status"] == "success"
        assert result["data"]["updated_fields"] == ["title"]
        # Message should be unchanged.
        assert state._job_registry["job_mod_1"]["message"] == "Keep Me"
        assert state._job_registry["job_mod_1"]["title"] == "New Title"

    def test_modify_only_message(self, mock_cfg, mock_scheduler):
        """Updating only message should leave title unchanged."""
        _seed_job(title="Keep Me", message="Old Message")
        result = notify(action="modify", job_id="job_mod_1",
                        title="", message="New Message")
        assert result["status"] == "success"
        assert result["data"]["updated_fields"] == ["message"]
        assert state._job_registry["job_mod_1"]["title"] == "Keep Me"
        assert state._job_registry["job_mod_1"]["message"] == "New Message"


class TestModifyValidation:
    """modify: parameter validation."""

    def test_modify_missing_job_id(self, mock_cfg, mock_scheduler):
        """Should return error when job_id is empty."""
        result = notify(action="modify", job_id="", title="New")
        assert result["status"] == "error"
        assert "job_id is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"

    def test_modify_no_fields_provided(self, mock_cfg, mock_scheduler):
        """Should return error when both title and message are empty."""
        _seed_job()
        result = notify(action="modify", job_id="job_mod_1", title="", message="")
        assert result["status"] == "error"
        assert "At least one of title or message" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"


class TestModifyNotFound:
    """modify: job not in registry."""

    def test_modify_job_not_found(self, mock_cfg, mock_scheduler):
        """Should return NOT_FOUND error when job_id not in registry."""
        result = notify(action="modify", job_id="nonexistent", title="New")
        assert result["status"] == "error"
        assert "not found in registry" in result["error"]
        assert result.get("error_code") == "NOT_FOUND"


class TestModifyTraceID:
    """modify: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in success response."""
        _seed_job()
        result = notify(action="modify", job_id="job_mod_1",
                        title="New", trace_id="trace-mod-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-mod-1"
        assert result["data"]["trace_id"] == "trace-mod-1"

    def test_trace_id_in_error_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in error response."""
        result = notify(action="modify", job_id="", trace_id="trace-mod-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-mod-2"
