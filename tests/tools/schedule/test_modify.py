"""modify action."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops import state


def test_modify_cron_schedule(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    m = schedule(action="modify", job_id=jid, cron="0 10 * * *")
    assert m["status"] == "success"
    assert m["data"]["action_status"] == "modified"
    assert "cron" in m["data"]["changed"]
    assert state._job_registry[jid]["cron"] == "0 10 * * *"
    # Trigger re-created: remove_job + add_job called.
    mock_scheduler.remove_job.assert_called_once_with(jid)


def test_modify_delivery(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    m = schedule(action="modify", job_id=jid, message="updated text")
    assert m["status"] == "success"
    assert state._job_registry[jid]["delivery"]["message"] == "updated text"


def test_modify_kind_mismatch(mock_cfg, mock_scheduler):
    """Cannot set cron on an interval job."""
    r = schedule(action="add_interval", interval="10m", message="a")
    jid = r["data"]["job_id"]
    m = schedule(action="modify", job_id=jid, cron="0 9 * * *")
    assert m["status"] == "error"
    assert m["error_code"] == "INVALID_PARAM"


def test_modify_not_found(mock_cfg, mock_scheduler):
    m = schedule(action="modify", job_id="nope", cron="0 9 * * *")
    assert m["status"] == "error"
    assert m["error_code"] == "NOT_FOUND"


def test_modify_cancelled_rejected(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    schedule(action="cancel", job_id=jid)
    m = schedule(action="modify", job_id=jid, cron="0 10 * * *")
    assert m["status"] == "error"
    assert m["error_code"] == "INVALID_STATE"


def test_modify_invalid_cron(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    m = schedule(action="modify", job_id=jid, cron="bad")
    assert m["status"] == "error"
    assert m["error_code"] == "INVALID_PARAM"


def test_modify_missing_job_id(mock_cfg, mock_scheduler):
    m = schedule(action="modify", cron="0 9 * * *")
    assert m["status"] == "error"
    assert m["error_code"] == "MISSING_PARAM"
