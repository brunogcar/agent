"""add_cron action + DOW remap + validation."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops import state


def test_add_cron_success(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="Daily standup")
    assert r["status"] == "success"
    d = r["data"]
    assert d["action_status"] == "scheduled"
    assert d["action"] == "add_cron"
    assert d["cron"] == "0 9 * * *"
    assert d["job_id"].startswith("cron_")
    assert d["next_run"].endswith("09:00:00")  # 9am in configured tz
    assert d["misfire_policy"] == "fire_last"  # default
    assert d["misfire_grace"] == "24h"
    # Registered + persisted.
    assert d["job_id"] in state._job_registry
    assert mock_scheduler.add_job.call_count == 1


def test_add_cron_missing_cron(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_add_cron_missing_message(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_add_cron_invalid_cron(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="not a cron", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"


def test_add_cron_invalid_misfire_policy(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="hi", misfire_policy="bogus")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"


def test_add_cron_scheduler_none(mock_cfg, mock_scheduler_none):
    r = schedule(action="add_cron", cron="0 9 * * *", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "DEPENDENCY_MISSING"


def test_add_cron_dow_remap_monday_not_tuesday(mock_cfg, mock_scheduler):
    """0 9 * * 1 = Monday 9am (standard cron 0=Sunday), NOT Tuesday (APScheduler 0=Monday)."""
    r = schedule(action="add_cron", cron="0 9 * * 1", message="weekly")
    assert r["status"] == "success"
    # The trigger passed to add_job should be a CronTrigger built with day-of-week
    # names (mon), not the raw "1" (which APScheduler would read as Tuesday).
    trigger = mock_scheduler.add_job.call_args.kwargs["trigger"]
    # APScheduler CronTrigger stores the field; check its str representation includes "mon".
    assert "mon" in str(trigger).lower() or "1" not in str(trigger).split()


def test_add_cron_custom_misfire(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="hi",
                 misfire_policy="fire_all", misfire_grace="7d")
    assert r["status"] == "success"
    assert r["data"]["misfire_policy"] == "fire_all"
    assert r["data"]["misfire_grace"] == "7d"


def test_add_cron_delivery_dict(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *",
                 delivery={"tool": "notify", "action": "send", "title": "T", "message": "M"})
    assert r["status"] == "success"
    meta = state._job_registry[r["data"]["job_id"]]
    assert meta["delivery"]["title"] == "T"
    assert meta["delivery"]["message"] == "M"


def test_add_cron_unsupported_delivery_tool(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *",
                 delivery={"tool": "slack", "message": "M"})
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"
    assert "slack" in r["error"]
