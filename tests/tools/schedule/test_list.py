"""list action."""
from __future__ import annotations

from tools.schedule import schedule


def test_list_empty(mock_cfg, mock_scheduler):
    r = schedule(action="list")
    assert r["status"] == "success"
    assert r["data"]["count"] == 0
    assert r["data"]["jobs"] == []


def test_list_with_jobs(mock_cfg, mock_scheduler):
    schedule(action="add_cron", cron="0 9 * * *", message="a")
    schedule(action="add_interval", interval="10m", message="b")
    r = schedule(action="list")
    assert r["data"]["count"] == 2
    kinds = {j["kind"] for j in r["data"]["jobs"]}
    assert kinds == {"cron", "interval"}


def test_list_scheduler_none_returns_empty(mock_cfg, mock_scheduler_none):
    r = schedule(action="list")
    assert r["status"] == "success"
    assert r["data"]["count"] == 0
    assert "not running" in r["data"]["note"].lower()


def test_list_next_run_for_cron(mock_cfg, mock_scheduler):
    schedule(action="add_cron", cron="0 9 * * *", message="a")
    r = schedule(action="list")
    assert r["data"]["jobs"][0]["next_run"].endswith("09:00:00")
