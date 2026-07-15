"""Tests for notify schedule action — schedule one-shot notification via APScheduler.

Covers:
  1. Success path (DateTrigger used, job added, registry updated)
  2. Missing message → error
  3. Missing/invalid delay_minutes → error
  4. APScheduler not installed → graceful error
  5. trace_id threading
  6. _job_registry updated with correct metadata
  7. _save_jobs() called (jobs.json persistence)
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from tools.notify import notify
from tools.notify_ops import state


class TestScheduleSuccess:
    """schedule: one-shot DateTrigger scheduling."""

    def test_schedule_success(self, mock_cfg, mock_scheduler):
        """Should schedule a DateTrigger job and return action_status=scheduled."""
        # Mock apscheduler.triggers.date.DateTrigger so the action's
        # `from apscheduler.triggers.date import DateTrigger` works even
        # without apscheduler installed.
        mock_date_trigger = MagicMock()
        mock_apscheduler = MagicMock()
        mock_apscheduler.triggers.date.DateTrigger = mock_date_trigger

        with patch.dict(sys.modules, {
            "apscheduler": mock_apscheduler,
            "apscheduler.triggers": mock_apscheduler.triggers,
            "apscheduler.triggers.date": mock_apscheduler.triggers.date,
        }):
            result = notify(action="schedule", message="wake up", delay_minutes=10, title="Alarm")

        assert result["status"] == "success"
        assert result["data"]["action_status"] == "scheduled"
        assert result["data"]["action"] == "schedule"
        assert result["data"]["job_id"].startswith("reminder_")
        assert "run_at" in result["data"]
        assert result["data"]["delay_minutes"] == 10
        mock_scheduler.add_job.assert_called_once()

    def test_schedule_uses_date_trigger(self, mock_cfg, mock_scheduler):
        """Should pass a DateTrigger instance to scheduler.add_job(trigger=...)."""
        # Use a real-ish DateTrigger mock so we can verify the trigger class used.
        with patch("apscheduler.triggers.date.DateTrigger") as mock_date_trigger:
            mock_date_trigger_instance = MagicMock()
            mock_date_trigger.return_value = mock_date_trigger_instance
            # Make the import path work even without apscheduler installed.
            mock_pkg = MagicMock()
            mock_pkg.triggers.date.DateTrigger = mock_date_trigger
            with patch.dict(sys.modules, {
                "apscheduler": mock_pkg,
                "apscheduler.triggers": mock_pkg.triggers,
                "apscheduler.triggers.date": mock_pkg.triggers.date,
            }):
                notify(action="schedule", message="hi", delay_minutes=5)

        # The trigger class should have been instantiated.
        mock_date_trigger.assert_called_once()
        # And add_job should have received the trigger instance.
        call_kwargs = mock_scheduler.add_job.call_args[1]
        assert call_kwargs["trigger"] is mock_date_trigger_instance


class TestScheduleValidation:
    """schedule: parameter validation."""

    def test_schedule_missing_message(self, mock_cfg, mock_scheduler):
        """Should return error when message is empty."""
        result = notify(action="schedule", message="", delay_minutes=5)
        assert result["status"] == "error"
        assert "message is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"
        mock_scheduler.add_job.assert_not_called()

    def test_schedule_missing_delay(self, mock_cfg, mock_scheduler):
        """Should return error when delay_minutes <= 0."""
        result = notify(action="schedule", message="wake up", delay_minutes=0)
        assert result["status"] == "error"
        assert "delay_minutes must be > 0" in result["error"]
        assert result.get("error_code") == "INVALID_PARAM"
        mock_scheduler.add_job.assert_not_called()

    def test_schedule_negative_delay(self, mock_cfg, mock_scheduler):
        """Negative delay should also error."""
        result = notify(action="schedule", message="wake up", delay_minutes=-5)
        assert result["status"] == "error"
        assert "delay_minutes must be > 0" in result["error"]


class TestScheduleNoAPScheduler:
    """schedule: graceful failure when APScheduler not installed."""

    def test_schedule_fails_when_apscheduler_missing(self, mock_cfg, mock_scheduler_none):
        """Should return DEPENDENCY_MISSING error when _get_scheduler returns None."""
        result = notify(action="schedule", message="wake up", delay_minutes=10)
        assert result["status"] == "error"
        assert "APScheduler not installed" in result["error"]
        assert result.get("error_code") == "DEPENDENCY_MISSING"


class TestScheduleTraceID:
    """schedule: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in success response."""
        mock_apscheduler = MagicMock()
        with patch.dict(sys.modules, {
            "apscheduler": mock_apscheduler,
            "apscheduler.triggers": mock_apscheduler.triggers,
            "apscheduler.triggers.date": mock_apscheduler.triggers.date,
        }):
            result = notify(action="schedule", message="hi", delay_minutes=5, trace_id="trace-sched-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-sched-1"
        assert result["data"]["trace_id"] == "trace-sched-1"

    def test_trace_id_in_error_response(self, mock_cfg, mock_scheduler_none):
        """trace_id should appear in error response."""
        result = notify(action="schedule", message="hi", delay_minutes=5, trace_id="trace-sched-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-sched-2"


class TestScheduleRegistryAndPersistence:
    """schedule: _job_registry updated and _save_jobs called."""

    def test_job_registry_updated_after_schedule(self, mock_cfg, mock_scheduler):
        """_job_registry should contain the new job after scheduling."""
        mock_apscheduler = MagicMock()
        with patch.dict(sys.modules, {
            "apscheduler": mock_apscheduler,
            "apscheduler.triggers": mock_apscheduler.triggers,
            "apscheduler.triggers.date": mock_apscheduler.triggers.date,
        }):
            result = notify(action="schedule", message="wake up", delay_minutes=10, title="Alarm")

        job_id = result["data"]["job_id"]
        assert job_id in state._job_registry
        meta = state._job_registry[job_id]
        assert meta["title"] == "Alarm"
        assert meta["message"] == "wake up"
        assert meta["status"] == "scheduled"
        assert meta["recurring"] is False
        assert meta["cron"] == ""
        assert "run_at" in meta

    def test_save_jobs_called_after_schedule(self, mock_cfg, mock_scheduler):
        """_save_jobs should be called after adding to registry (persistence)."""
        mock_apscheduler = MagicMock()
        with patch.dict(sys.modules, {
            "apscheduler": mock_apscheduler,
            "apscheduler.triggers": mock_apscheduler.triggers,
            "apscheduler.triggers.date": mock_apscheduler.triggers.date,
        }), patch("tools.notify_ops.state._save_jobs") as mock_save:
            notify(action="schedule", message="hi", delay_minutes=5)

        mock_save.assert_called_once()

    def test_jobs_json_persisted_to_disk(self, mock_cfg, mock_scheduler, tmp_path):
        """_save_jobs should write a real jobs.json file under workspace_root.

        This test exercises the actual _save_jobs() (not mocked) to verify
        the persistence file is created and contains valid JSON.
        """
        mock_apscheduler = MagicMock()
        with patch.dict(sys.modules, {
            "apscheduler": mock_apscheduler,
            "apscheduler.triggers": mock_apscheduler.triggers,
            "apscheduler.triggers.date": mock_apscheduler.triggers.date,
        }):
            result = notify(action="schedule", message="persist me", delay_minutes=5)

        jobs_file = (tmp_path / "workspace" / ".notify_jobs" / "jobs.json")
        assert jobs_file.exists(), f"jobs.json not written at {jobs_file}"
        import json
        loaded = json.loads(jobs_file.read_text(encoding="utf-8"))
        job_id = result["data"]["job_id"]
        assert job_id in loaded
        assert loaded[job_id]["message"] == "persist me"
