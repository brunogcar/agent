"""history action."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops.helpers import _fire_job


def test_history_empty(mock_cfg, mock_scheduler):
    r = schedule(action="history")
    assert r["status"] == "success"
    assert r["data"]["count"] == 0


def test_history_after_fire(mock_cfg, mock_scheduler, mock_notify):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    _fire_job(job_id=jid)  # live fire → logged
    h = schedule(action="history")
    assert h["data"]["count"] == 1
    assert h["data"]["deliveries"][0]["job_id"] == jid
    assert h["data"]["deliveries"][0]["catch_up"] is False


def test_history_limit(mock_cfg, mock_scheduler, mock_notify):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    for _ in range(5):
        _fire_job(job_id=jid)
    h = schedule(action="history", limit=3)
    assert h["data"]["count"] == 3


def test_history_limit_clamped(mock_cfg, mock_scheduler):
    r = schedule(action="history", limit=99999)
    assert r["status"] == "success"  # clamped to 100, no error
