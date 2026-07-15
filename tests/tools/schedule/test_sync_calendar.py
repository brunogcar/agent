"""sync_calendar action — mocked httpx + .ics parsing."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from core.time_utils import now
from tools.schedule import schedule
from tools.schedule_ops import state


# A minimal .ics with 3 VEVENTs: one future, one past, one with RRULE.
def _future_iso():
    return (now() + timedelta(hours=6)).strftime("%Y%m%dT%H%M%S")


def _past_iso():
    return (now() - timedelta(days=2)).strftime("%Y%m%dT%H%M%S")


_ICS = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:fut@x
DTSTART:{_future_iso()}
SUMMARY:Future meeting
DESCRIPTION:Bring notes
END:VEVENT
BEGIN:VEVENT
UID:past@x
DTSTART:{_past_iso()}
SUMMARY:Past event
END:VEVENT
BEGIN:VEVENT
UID:rr@x
DTSTART:{_future_iso()}
SUMMARY:Recurring daily
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
"""


def _mock_response(text=_ICS):
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def test_sync_success(mock_cfg, mock_scheduler):
    with patch("httpx.get", return_value=_mock_response()):
        r = schedule(action="sync_calendar", calendar_url="https://example.com/cal.ics")
    assert r["status"] == "success"
    d = r["data"]
    assert d["action_status"] == "synced"
    assert d["events_found"] == 3
    # 2 future (one plain, one RRULE first-occurrence) + 1 past skipped.
    assert d["events_scheduled"] == 2
    assert d["events_skipped_past"] == 1
    assert d["rrule_skipped"] == 1
    assert len(d["jobs"]) == 2
    for jid in d["jobs"]:
        assert state._job_registry[jid]["kind"] == "once"
        assert state._job_registry[jid]["fire_if_missed"] is True


def test_sync_invalid_url_scheme(mock_cfg, mock_scheduler):
    r = schedule(action="sync_calendar", calendar_url="ftp://x/y.ics")
    assert r["status"] == "error"
    assert r["error_code"] == "INVALID_PARAM"


def test_sync_missing_url(mock_cfg, mock_scheduler):
    r = schedule(action="sync_calendar")
    assert r["status"] == "error"
    assert r["error_code"] == "MISSING_PARAM"


def test_sync_fetch_error(mock_cfg, mock_scheduler):
    with patch("httpx.get", side_effect=Exception("network down")):
        r = schedule(action="sync_calendar", calendar_url="https://example.com/cal.ics")
    assert r["status"] == "error"
    assert r["error_code"] == "CONNECT_ERROR"


def test_sync_all_day_event(mock_cfg, mock_scheduler):
    ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:d@x
DTSTART;VALUE=DATE:20990101
SUMMARY:All-day in 2099
END:VEVENT
END:VCALENDAR
"""
    with patch("httpx.get", return_value=_mock_response(ics)):
        r = schedule(action="sync_calendar", calendar_url="https://example.com/cal.ics")
    assert r["status"] == "success"
    assert r["data"]["events_scheduled"] == 1


def test_sync_scheduler_none(mock_cfg, mock_scheduler_none):
    r = schedule(action="sync_calendar", calendar_url="https://example.com/cal.ics")
    assert r["status"] == "error"
    assert r["error_code"] == "DEPENDENCY_MISSING"
