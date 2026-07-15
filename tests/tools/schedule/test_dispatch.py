"""Facade dispatch + Literal enum + unknown/empty action."""
from __future__ import annotations

from tools.schedule import schedule


def test_schedule_is_callable():
    assert callable(schedule)


def test_action_literal_has_all_9_actions():
    from typing import get_args
    actions = set(get_args(schedule.__annotations__["action"]))
    assert actions == {"add_cron", "add_interval", "add_once", "list",
                        "cancel", "modify", "history", "sync_calendar", "test"}


def test_empty_action_returns_error(mock_cfg):
    r = schedule(action="")
    assert r["status"] == "error"
    assert "action is required" in r["error"]


def test_unknown_action_returns_error_with_valid_list(mock_cfg):
    r = schedule(action="bogus")
    assert r["status"] == "error"
    assert "Unknown action 'bogus'" in r["error"]
    for a in ("add_cron", "list", "cancel"):
        assert a in r["error"]


def test_facade_adds_duration_ms(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="hi")
    assert r["status"] == "success"
    assert "duration_ms" in r
    assert isinstance(r["duration_ms"], (int, float))


def test_handler_exception_caught(mock_cfg, mock_scheduler):
    """If a handler raises, the facade returns error (not a crash)."""
    from tools.schedule_ops._registry import DISPATCH
    orig = DISPATCH["schedule"]["add_cron"]["func"]
    def _boom(**kw):
        raise RuntimeError("boom")
    DISPATCH["schedule"]["add_cron"]["func"] = _boom
    try:
        r = schedule(action="add_cron", cron="0 9 * * *", message="hi")
        assert r["status"] == "error"
        assert "Schedule action failed" in r["error"]
    finally:
        DISPATCH["schedule"]["add_cron"]["func"] = orig
