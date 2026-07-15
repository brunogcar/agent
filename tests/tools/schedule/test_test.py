"""test action (fire a test delivery immediately)."""
from __future__ import annotations

from tools.schedule import schedule


def test_test_fires_notify(mock_cfg, mock_scheduler, mock_notify):
    r = schedule(action="test")
    assert r["status"] == "success"
    assert r["data"]["action_status"] == "ok"
    mock_notify.assert_called_once()
    kw = mock_notify.call_args.kwargs
    assert kw["action"] == "send"
    assert "test" in kw["title"].lower() or "test" in kw["message"].lower()


def test_test_custom(mock_cfg, mock_scheduler, mock_notify):
    r = schedule(action="test", title="Ping", message="hello")
    assert r["status"] == "success"
    kw = mock_notify.call_args.kwargs
    assert kw["title"] == "Ping"
    assert kw["message"] == "hello"


def test_test_no_job_created(mock_cfg, mock_scheduler, mock_notify):
    schedule(action="test")
    # list should be empty — no job scheduled.
    r = schedule(action="list")
    assert r["data"]["count"] == 0
