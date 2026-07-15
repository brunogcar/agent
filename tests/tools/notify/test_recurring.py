"""Tests for notify recurring action — cron-style recurring notification. [NEW]

Covers:
  1. Success path (CronTrigger used, job added, registry updated)
  2. Missing message → error
  3. Missing cron → error
  4. Invalid cron expression → error
  5. APScheduler not installed → graceful error
  6. trace_id threading
  7. CronTrigger.from_crontab actually invoked
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from tools.notify import notify
from tools.notify_ops import state


def _mock_apscheduler_with_cron():
    """Build a mock apscheduler package that exposes CronTrigger.from_crontab.

    Returns (mock_pkg, mock_cron_trigger_cls, mock_cron_trigger_instance).
    Used to patch sys.modules so `from apscheduler.triggers.cron import CronTrigger`
    works even when real apscheduler isn't installed in the test venv.
    """
    mock_cron_instance = MagicMock()
    mock_cron_instance.get_next_fire_time.return_value = None  # or set later
    mock_cron_trigger = MagicMock(return_value=mock_cron_instance)
    mock_cron_trigger.from_crontab = MagicMock(return_value=mock_cron_instance)

    mock_pkg = MagicMock()
    mock_pkg.triggers.cron.CronTrigger = mock_cron_trigger

    return mock_pkg, mock_cron_trigger, mock_cron_instance


class TestRecurringSuccess:
    """recurring: cron-style scheduling success."""

    def test_recurring_success(self, mock_cfg, mock_scheduler):
        """Should schedule a CronTrigger job and return action_status=scheduled."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="0 9 * * *",
                            title="Standup", message="Daily standup")

        assert result["status"] == "success"
        assert result["data"]["action_status"] == "scheduled"
        assert result["data"]["action"] == "recurring"
        assert result["data"]["job_id"].startswith("recurring_")
        assert result["data"]["cron"] == "0 9 * * *"
        assert result["data"]["title"] == "Standup"
        assert result["data"]["message"] == "Daily standup"
        mock_scheduler.add_job.assert_called_once()

    def test_recurring_uses_cron_trigger_from_crontab(self, mock_cfg, mock_scheduler):
        """Should call CronTrigger.from_crontab(cron) and pass result to add_job."""
        mock_pkg, mock_cron_trigger, mock_cron_instance = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            notify(action="recurring", cron="*/5 * * * *", message="heartbeat")

        mock_cron_trigger.from_crontab.assert_called_once_with("*/5 * * * *")
        call_kwargs = mock_scheduler.add_job.call_args[1]
        assert call_kwargs["trigger"] is mock_cron_instance

    def test_recurring_default_title_is_agent_reminder(self, mock_cfg, mock_scheduler):
        """When title is empty, default 'Agent Reminder' should be used."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="0 9 * * *", message="hi")
        assert result["data"]["title"] == "Agent Reminder"

    def test_recurring_registry_marks_recurring_true(self, mock_cfg, mock_scheduler):
        """_job_registry entry should have recurring=True and cron set."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="0 9 * * *", message="hi")
        job_id = result["data"]["job_id"]
        meta = state._job_registry[job_id]
        assert meta["recurring"] is True
        assert meta["cron"] == "0 9 * * *"
        assert meta["status"] == "recurring"

    def test_recurring_save_jobs_called(self, mock_cfg, mock_scheduler):
        """_save_jobs should be called after registering the recurring job."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }), patch("tools.notify_ops.state._save_jobs") as mock_save:
            notify(action="recurring", cron="0 9 * * *", message="hi")
        mock_save.assert_called_once()


class TestRecurringValidation:
    """recurring: parameter validation."""

    def test_recurring_missing_message(self, mock_cfg, mock_scheduler):
        """Should return error when message is empty."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="0 9 * * *", message="")
        assert result["status"] == "error"
        assert "message is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"
        mock_scheduler.add_job.assert_not_called()

    def test_recurring_missing_cron(self, mock_cfg, mock_scheduler):
        """Should return error when cron is empty."""
        result = notify(action="recurring", cron="", message="hi")
        assert result["status"] == "error"
        assert "cron is required" in result["error"]
        assert result.get("error_code") == "MISSING_PARAM"

    def test_recurring_whitespace_cron_treated_as_empty(self, mock_cfg, mock_scheduler):
        """Whitespace-only cron should be treated as empty."""
        result = notify(action="recurring", cron="   ", message="hi")
        assert result["status"] == "error"
        assert "cron is required" in result["error"]


class TestRecurringInvalidCron:
    """recurring: invalid cron expression handling."""

    def test_recurring_invalid_cron_expression(self, mock_cfg, mock_scheduler):
        """Should return INVALID_PARAM error when cron expression is malformed."""
        # Make from_crontab raise ValueError (what real APScheduler does).
        mock_pkg, mock_cron_trigger, _ = _mock_apscheduler_with_cron()
        mock_cron_trigger.from_crontab.side_effect = ValueError("wrong number of fields")
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="not a cron", message="hi")
        assert result["status"] == "error"
        assert "Invalid cron expression" in result["error"]
        assert result.get("error_code") == "INVALID_PARAM"
        mock_scheduler.add_job.assert_not_called()


class TestRecurringNoAPScheduler:
    """recurring: graceful failure when APScheduler not installed."""

    def test_recurring_fails_when_apscheduler_missing(self, mock_cfg, mock_scheduler_none):
        """Should return DEPENDENCY_MISSING error when _get_scheduler returns None."""
        result = notify(action="recurring", cron="0 9 * * *", message="hi")
        assert result["status"] == "error"
        assert "APScheduler not installed" in result["error"]
        assert result.get("error_code") == "DEPENDENCY_MISSING"


class TestRecurringTraceID:
    """recurring: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in success response."""
        mock_pkg, _, _ = _mock_apscheduler_with_cron()
        with patch.dict(sys.modules, {
            "apscheduler": mock_pkg,
            "apscheduler.triggers": mock_pkg.triggers,
            "apscheduler.triggers.cron": mock_pkg.triggers.cron,
        }):
            result = notify(action="recurring", cron="0 9 * * *",
                            message="hi", trace_id="trace-recur-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-recur-1"
        assert result["data"]["trace_id"] == "trace-recur-1"

    def test_trace_id_in_error_response(self, mock_cfg, mock_scheduler):
        """trace_id should appear in error response."""
        result = notify(action="recurring", cron="", message="hi", trace_id="trace-recur-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-recur-2"
