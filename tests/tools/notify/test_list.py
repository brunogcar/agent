"""Tests for notify list action — list scheduled jobs.

Covers:
  1. Returns jobs (with metadata enrichment from _job_registry)
  2. Empty list when no jobs scheduled
  3. Scheduler not running → empty list with note (NOT an error)
  4. trace_id threading
  5. Recurring jobs include the cron field
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.notify import notify
from tools.notify_ops import state


class TestListSuccess:
    """list: returns scheduled jobs."""

    def test_list_returns_jobs(self, mock_cfg, mock_scheduler):
        """Should return job list enriched with registry metadata."""
        # Set up a fake job in APScheduler + matching registry entry.
        mock_job = MagicMock()
        mock_job.id = "job_1"
        mock_job.next_run_time = "2099-01-01 12:00:00"
        mock_scheduler.get_jobs.return_value = [mock_job]

        state._job_registry["job_1"] = {
            "title": "Test Title",
            "message": "Test Message",
            "run_at": "2099-01-01T12:00:00",
            "cron": "",
            "status": "scheduled",
            "recurring": False,
        }

        result = notify(action="list")
        assert result["status"] == "success"
        assert result["data"]["action_status"] == "ok"
        assert result["data"]["action"] == "list"
        assert result["data"]["count"] == 1
        jobs = result["data"]["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "job_1"
        assert jobs[0]["run_at"] == "2099-01-01 12:00:00"
        assert jobs[0]["title"] == "Test Title"
        assert jobs[0]["message"] == "Test Message"
        assert jobs[0]["recurring"] is False
        # Non-recurring jobs should NOT include cron field
        assert "cron" not in jobs[0]

    def test_list_includes_cron_for_recurring_jobs(self, mock_cfg, mock_scheduler):
        """Recurring jobs should include the cron field in list output."""
        mock_job = MagicMock()
        mock_job.id = "recurring_1"
        mock_job.next_run_time = "2099-01-01 09:00:00"
        mock_scheduler.get_jobs.return_value = [mock_job]

        state._job_registry["recurring_1"] = {
            "title": "Daily Standup",
            "message": "Standup time",
            "run_at": "",
            "cron": "0 9 * * *",
            "status": "recurring",
            "recurring": True,
        }

        result = notify(action="list")
        jobs = result["data"]["jobs"]
        assert jobs[0]["recurring"] is True
        assert jobs[0]["cron"] == "0 9 * * *"

    def test_list_empty_when_no_jobs(self, mock_cfg, mock_scheduler):
        """Should return empty list (count=0) when no jobs scheduled."""
        mock_scheduler.get_jobs.return_value = []
        result = notify(action="list")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["jobs"] == []


class TestListNoScheduler:
    """list: scheduler not running."""

    def test_list_returns_empty_with_note_when_scheduler_none(self, mock_cfg, mock_scheduler_none):
        """Should return empty list with note (NOT an error) when scheduler is None.

        list() is intentionally tolerant of the missing-scheduler case so
        callers can defensively call list() without conditional logic.
        """
        result = notify(action="list")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["jobs"] == []
        assert "note" in result["data"]
        assert "Scheduler not running" in result["data"]["note"]


class TestListTraceID:
    """list: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in success response."""
        mock_scheduler.get_jobs.return_value = []
        result = notify(action="list", trace_id="trace-list-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-list-1"
        assert result["data"]["trace_id"] == "trace-list-1"
