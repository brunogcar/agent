"""Tests for notify cancel action — remove scheduled/recurring job by job_id.

Covers:
  1. Success path (job removed from scheduler + registry)
  2. Missing job_id → error
  3. Job not found in registry → error
  4. Scheduler not running → error
  5. trace_id threading
  6. _save_jobs called after cancel
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.notify import notify
from tools.notify_ops import state


class TestCancelSuccess:
    """cancel: successful job removal."""

    def test_cancel_removes_job(self, mock_cfg, mock_scheduler):
        """Should call scheduler.remove_job and remove from _job_registry."""
        # Pre-populate the registry with a fake scheduled job.
        state._job_registry["test_job_123"] = {
            "title": "T",
            "message": "M",
            "run_at": "2099-01-01T00:00:00",
            "cron": "",
            "status": "scheduled",
            "recurring": False,
        }

        result = notify(action="cancel", job_id="test_job_123")

        assert result["status"] == "success"
        assert result["data"]["action_status"] == "cancelled"
        assert result["data"]["action"] == "cancel"
        assert result["data"]["job_id"] == "test_job_123"
        mock_scheduler.remove_job.assert_called_once_with("test_job_123")
        assert "test_job_123" not in state._job_registry

    def test_cancel_saves_jobs_after_removal(self, mock_cfg, mock_scheduler):
        """_save_jobs should be called after removing the job from registry."""
        state._job_registry["job_xyz"] = {
            "title": "T", "message": "M", "run_at": "2099-01-01T00:00:00",
            "cron": "", "status": "scheduled", "recurring": False,
        }
        with patch("tools.notify_ops.state._save_jobs") as mock_save:
            notify(action="cancel", job_id="job_xyz")
        mock_save.assert_called_once()

    def test_cancel_succeeds_even_if_scheduler_remove_raises(self, mock_cfg, mock_scheduler):
        """If scheduler.remove_job raises (job already fired), still remove from registry.

        APScheduler raises JobLookupError if the job already ran and was
        auto-removed. We should still pop from our registry to keep state
        consistent and return success — the user's intent (don't fire this
        job again) is satisfied either way.
        """
        state._job_registry["job_already_fired"] = {
            "title": "T", "message": "M", "run_at": "2000-01-01T00:00:00",
            "cron": "", "status": "scheduled", "recurring": False,
        }
        mock_scheduler.remove_job.side_effect = Exception("JobLookupError: job not found")

        result = notify(action="cancel", job_id="job_already_fired")
        assert result["status"] == "success"
        assert "job_already_fired" not in state._job_registry


class TestCancelValidation:
    """cancel: parameter validation."""

    def test_cancel_missing_job_id(self, mock_cfg, mock_scheduler):
        """Should return error when job_id is empty."""
        result = notify(action="cancel", job_id="")
        assert result["status"] == "error"
        assert "job_id is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"
        mock_scheduler.remove_job.assert_not_called()


class TestCancelNotFound:
    """cancel: job not in registry."""

    def test_cancel_job_not_found(self, mock_cfg, mock_scheduler):
        """Should return NOT_FOUND error when job_id not in registry."""
        result = notify(action="cancel", job_id="nonexistent_job")
        assert result["status"] == "error"
        assert "not found in registry" in result["error"]
        assert result.get("error_code") == "NOT_FOUND"
        mock_scheduler.remove_job.assert_not_called()


class TestCancelNoScheduler:
    """cancel: scheduler not running."""

    def test_cancel_fails_when_scheduler_not_running(self, mock_cfg, mock_scheduler_none):
        """Should return DEPENDENCY_MISSING when scheduler is None.

        We pre-populate the registry so the NOT_FOUND check passes — this
        isolates the scheduler-not-running path.
        """
        state._job_registry["job_x"] = {
            "title": "T", "message": "M", "run_at": "2099-01-01T00:00:00",
            "cron": "", "status": "scheduled", "recurring": False,
        }
        result = notify(action="cancel", job_id="job_x")
        assert result["status"] == "error"
        assert "Scheduler not running" in result["error"]
        assert result.get("error_code") == "DEPENDENCY_MISSING"


class TestCancelTraceID:
    """cancel: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in success response."""
        state._job_registry["job_t"] = {
            "title": "T", "message": "M", "run_at": "2099-01-01T00:00:00",
            "cron": "", "status": "scheduled", "recurring": False,
        }
        result = notify(action="cancel", job_id="job_t", trace_id="trace-cancel-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-cancel-1"
        assert result["data"]["trace_id"] == "trace-cancel-1"

    def test_trace_id_in_error_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in error response."""
        result = notify(action="cancel", job_id="", trace_id="trace-cancel-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-cancel-2"
