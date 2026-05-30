"""
tests/tools/notify/test_notify.py
Deep tests for the notify meta-tool (send, schedule, cancel, list).
"""
from __future__ import annotations
import sys
import pytest
from unittest.mock import patch, MagicMock
from tools.notify import notify, _job_registry

class TestNotifyValidation:
    def test_unknown_action_returns_error(self):
        result = notify(action="explode", message="boom")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_send_requires_message(self):
        result = notify(action="send", message="")
        assert result["status"] == "error"
        assert "message is required" in result["error"]

    def test_schedule_requires_message(self):
        result = notify(action="schedule", message="", delay_minutes=5)
        assert result["status"] == "error"
        assert "message is required" in result["error"]

    def test_schedule_requires_positive_delay(self):
        result = notify(action="schedule", message="test", delay_minutes=0)
        assert result["status"] == "error"
        assert "delay_minutes must be > 0" in result["error"]

    def test_cancel_requires_job_id(self):
        result = notify(action="cancel", job_id="")
        assert result["status"] == "error"
        assert "job_id is required" in result["error"]

class TestNotifySend:
    def test_send_fallback_to_console_on_plyer_failure(self):
        """If plyer fails, it must fall back to console and still return success."""
        with patch("tools.notify.cfg") as mock_cfg, \
             patch("plyer.notification.notify") as mock_plyer_notify:
            mock_cfg.is_windows = True
            mock_plyer_notify.side_effect = Exception("Plyer crashed")
            
            result = notify(action="send", message="test fallback")
            
        assert result["status"] == "sent"
        assert result["method"] == "console"

class TestNotifySchedule:
    def test_schedule_returns_job_id_and_run_at(self):
        mock_scheduler = MagicMock()
        mock_date_trigger = MagicMock()
        
        # 🔴 FIX: Mock apscheduler modules in sys.modules so the test passes 
        # even if apscheduler is not installed in the current venv.
        mock_apscheduler = MagicMock()
        mock_apscheduler.triggers.date.DateTrigger = mock_date_trigger
        
        with patch("tools.notify._get_scheduler", return_value=mock_scheduler), \
             patch.dict(sys.modules, {
                 "apscheduler": mock_apscheduler,
                 "apscheduler.triggers": mock_apscheduler.triggers,
                 "apscheduler.triggers.date": mock_apscheduler.triggers.date
             }):
            result = notify(action="schedule", message="wake up", delay_minutes=10, title="Alarm")
            
        assert result["status"] == "scheduled", f"Failed with: {result.get('error')}"
        assert "job_id" in result
        assert result["job_id"].startswith("reminder_")
        assert "run_at" in result
        assert mock_scheduler.add_job.called

    def test_schedule_fails_if_no_apscheduler(self):
        with patch("tools.notify._get_scheduler", return_value=None):
            result = notify(action="schedule", message="wake up", delay_minutes=10)
            
        assert result["status"] == "error"
        assert "APScheduler not installed" in result["error"]

class TestNotifyCancelAndList:
    def test_cancel_removes_job(self):
        mock_scheduler = MagicMock()
        _job_registry["test_job_123"] = {"title": "t", "message": "m"}
        
        with patch("tools.notify._get_scheduler", return_value=mock_scheduler):
            result = notify(action="cancel", job_id="test_job_123")
            
        assert result["status"] == "cancelled"
        assert mock_scheduler.remove_job.called
        assert "test_job_123" not in _job_registry

    def test_list_returns_jobs_array(self):
        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "job_1"
        mock_job.next_run_time = "2026-05-31 12:00:00"
        mock_scheduler.get_jobs.return_value = [mock_job]
        _job_registry["job_1"] = {"title": "Test", "message": "Msg"}
        
        with patch("tools.notify._get_scheduler", return_value=mock_scheduler):
            result = notify(action="list")
            
        assert result["status"] == "ok"
        assert "jobs" in result
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["job_id"] == "job_1"