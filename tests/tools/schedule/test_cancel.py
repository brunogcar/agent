"""cancel action."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops import state


def test_cancel_success(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    c = schedule(action="cancel", job_id=jid)
    assert c["status"] == "success"
    assert c["data"]["action_status"] == "cancelled"
    assert state._job_registry[jid]["status"] == "cancelled"
    mock_scheduler.remove_job.assert_called_once_with(jid)


def test_cancel_missing_job_id(mock_cfg, mock_scheduler):
    r = schedule(action="cancel")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_cancel_not_found(mock_cfg, mock_scheduler):
    r = schedule(action="cancel", job_id="nope")
    assert r["status"] == "error"
    assert r["error_code"] == "NOT_FOUND"


def test_cancel_already_fired_is_noop(mock_cfg, mock_scheduler):
    """remove_job raising (already fired) is swallowed — cancel still marks cancelled."""
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    mock_scheduler.remove_job.side_effect = Exception("not found")
    c = schedule(action="cancel", job_id=jid)
    assert c["status"] == "success"
