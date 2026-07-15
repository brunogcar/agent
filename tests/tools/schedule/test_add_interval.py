"""add_interval action + validation."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops import state


def test_add_interval_success(mock_cfg, mock_scheduler):
    r = schedule(action="add_interval", interval="10m", message="Heartbeat")
    assert r["status"] == "success"
    d = r["data"]
    assert d["action_status"] == "scheduled"
    assert d["interval"] == "10m"
    assert d["job_id"].startswith("int_")
    assert d["misfire_policy"] == "fire_last"
    assert d["job_id"] in state._job_registry


def test_add_interval_compound(mock_cfg, mock_scheduler):
    r = schedule(action="add_interval", interval="1h30m", message="hi")
    assert r["status"] == "success"


def test_add_interval_missing(mock_cfg, mock_scheduler):
    r = schedule(action="add_interval", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_add_interval_invalid(mock_cfg, mock_scheduler):
    r = schedule(action="add_interval", interval="banana", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"


def test_add_interval_scheduler_none(mock_cfg, mock_scheduler_none):
    r = schedule(action="add_interval", interval="10m", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "DEPENDENCY_MISSING"
