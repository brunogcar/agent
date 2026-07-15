"""add_once action + human-time parsing + past rejection."""
from __future__ import annotations

from tools.schedule import schedule
from tools.schedule_ops import state


def test_add_once_relative(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", run_at="in 30m", message="Coffee")
    assert r["status"] == "success"
    assert r["data"]["job_id"].startswith("once_")
    assert r["data"]["run_at"].endswith(":") or ":" in r["data"]["run_at"]  # a timestamp


def test_add_once_iso(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", run_at="2026-07-16T09:00:00", message="Deploy")
    assert r["status"] == "success"
    assert "09:00:00" in r["data"]["run_at"]


def test_add_once_past_rejected(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", run_at="2020-01-01T00:00:00", message="old")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"
    assert "past" in r["error"].lower()


def test_add_once_missing(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", message="hi")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_add_once_fire_if_missed(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", run_at="in 1h", message="x", fire_if_missed=True)
    assert r["status"] == "success"
    assert r["data"]["fire_if_missed"] is True
    meta = state._job_registry[r["data"]["job_id"]]
    assert meta["fire_if_missed"] is True


def test_add_once_invalid_run_at(mock_cfg, mock_scheduler):
    r = schedule(action="add_once", run_at="banana", message="x")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"


def test_add_once_scheduler_none(mock_cfg, mock_scheduler_none):
    r = schedule(action="add_once", run_at="in 1h", message="x")
    assert r["status"] == "error"
    assert r["error_code"] == "DEPENDENCY_MISSING"
