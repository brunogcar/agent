"""tools/schedule_ops/actions/sync_calendar.py — Sync an iCal (.ics) calendar.

Fetches a remote .ics URL, parses VEVENTs, and creates one-shot jobs for each
upcoming event (delivered via notify at the event's start time).

v1.0 SCOPE (deliberately minimal):
  - Fetches .ics over http(s) via httpx (timeout 15s).
  - Parses VEVENT DTSTART / SUMMARY / DESCRIPTION / UID.
  - Creates add_once jobs for events with DTSTART in the future.
  - Honors DTSTART TZID (named tz) and VALUE=DATE (all-day → midnight).
  - Line-unfolding per RFC 5545 (lines starting with space/tab continue prev).

DEFERRED (roadmap, v2.0+):
  - RRULE recurrence expansion (recurring events → only first occurrence
    scheduled; RRULE noted in the response as `rrule_skipped`).
  - CalDAV two-way sync (read+write, ETag-based change detection).
  - VTODO (tasks), VALARM (per-event reminders), EXDATE (exceptions).
  - Authentication (private CalDAV needs Basic/Bearer auth).
"""
from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone as _tz

from core.contracts import ok, fail
from core.time_utils import parse_iso, now, format_dt, get_timezone
from tools.schedule_ops._registry import register_action
from tools.schedule_ops import helpers
from tools.schedule_ops import state


def _fetch_ics(url: str, timeout: float = 15.0) -> str:
    """Fetch .ics content. Raises on HTTP error / non-text content."""
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _unfold_lines(raw: str) -> list[str]:
    """RFC 5545 line unfolding: a line starting with space/tab continues the previous."""
    out: list[str] = []
    for line in raw.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


_DTSTART_RE = re.compile(r"^DTSTART(?:;([^:]*))?:(.*)$")


def _parse_ics_dt(value: str, params: str) -> datetime:
    """Parse an iCal DTSTART value (with optional params) to a tz-aware datetime.

    Handles: YYYYMMDDTHHMMSSZ (UTC), YYYYMMDDTHHMMSS (local/configured tz),
    YYYYMMDDTHHMMSS with TZID param, VALUE=DATE (YYYYMMDD → midnight).
    """
    params = params or ""
    value = value.strip()
    # All-day date.
    if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=get_timezone())
    # UTC (trailing Z).
    if value.endswith("Z"):
        d = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S")
        return d.replace(tzinfo=_tz.utc).astimezone(get_timezone())
    # Named TZID.
    tzid_m = re.search(r"TZID=([^;:]+)", params, re.IGNORECASE)
    if tzid_m:
        from zoneinfo import ZoneInfo
        try:
            tz = ZoneInfo(tzid_m.group(1))
            d = datetime.strptime(value, "%Y%m%dT%H%M%S")
            return d.replace(tzinfo=tz)
        except Exception:
            pass  # fall through to local
    # Local (naive) → assume configured tz.
    d = datetime.strptime(value, "%Y%m%dT%H%M%S")
    return d.replace(tzinfo=get_timezone())


def _parse_vevents(raw: str) -> list[dict]:
    """Parse .ics text into a list of VEVENT dicts."""
    lines = _unfold_lines(raw)
    events: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            cur = {}
        elif line.strip() == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None:
            # Split property name (with optional params) from value.
            if ":" in line:
                head, _, val = line.partition(":")
                key = head.split(";", 1)[0].upper()
                params = head.split(";", 1)[1] if ";" in head else ""
                if key == "DTSTART":
                    try:
                        cur["dtstart"] = _parse_ics_dt(val, params)
                    except Exception as e:
                        cur["dtstart_error"] = str(e)
                elif key == "SUMMARY":
                    cur["summary"] = val.strip()
                elif key == "DESCRIPTION":
                    cur["description"] = val.strip()
                elif key == "UID":
                    cur["uid"] = val.strip()
                elif key == "RRULE":
                    cur["rrule"] = val.strip()
    return events


@register_action(
    "schedule", "sync_calendar",
    help_text="""sync_calendar — Sync an iCal (.ics) calendar URL into scheduled jobs.
Required: calendar_url (http(s) URL to a .ics file)
Optional: name (prefix for created jobs), trace_id
Returns: {action_status: "synced", events_found, events_scheduled, events_skipped_past,
          rrule_skipped, jobs: [job_id...], trace_id?}

v1.0: parses VEVENT DTSTART/SUMMARY/DESCRIPTION; creates add_once jobs for
upcoming events. RRULE recurrence + CalDAV two-way sync are deferred (v2.0+).""",
    examples=[
        'schedule(action="sync_calendar", calendar_url="https://calendar.google.com/calendar/ical/.../basic.ics")',
    ],
)
def _action_sync_calendar(
    calendar_url: str = "",
    name: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    if not calendar_url or not calendar_url.strip():
        return fail("calendar_url is required for sync_calendar",
                    trace_id=trace_id, error_code="MISSING_PARAM")
    url = calendar_url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return fail("calendar_url must be an http(s) URL",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    scheduler = helpers._get_scheduler()
    if scheduler is None:
        return fail("APScheduler not installed. Run: pip install apscheduler",
                    trace_id=trace_id, error_code="DEPENDENCY_MISSING")

    try:
        raw = _fetch_ics(url)
    except Exception as e:
        return fail(f"Failed to fetch calendar: {e}",
                    trace_id=trace_id, error_code="CONNECT_ERROR")

    try:
        events = _parse_vevents(raw)
    except Exception as e:
        return fail(f"Failed to parse .ics: {e}",
                    trace_id=trace_id, error_code="INVALID_PARAM")

    n = now()
    prefix = (name or "calendar").strip()
    jobs_created: list[str] = []
    skipped_past = 0
    rrule_skipped = 0
    parse_errors = 0

    for ev in events:
        dt = ev.get("dtstart")
        if dt is None:
            parse_errors += 1
            continue
        if dt <= n:
            skipped_past += 1
            continue
        if ev.get("rrule"):
            # RRULE expansion deferred — schedule the first occurrence only,
            # but count it so the user knows recurrence isn't fully synced.
            rrule_skipped += 1
        summary = ev.get("summary", "(no title)")
        desc = ev.get("description", "")
        msg = desc if desc else summary
        job_id = f"cal_{int(_time.time() * 1000)}_{len(jobs_created)}"
        deliv = helpers._resolve_delivery(None, title=summary, message=msg, name=prefix)
        try:
            from apscheduler.triggers.date import DateTrigger
            scheduler.add_job(
                func=state._noop_fire, trigger=DateTrigger(run_date=dt),
                kwargs={"job_id": job_id}, id=job_id, replace_existing=True,
            )
        except Exception:
            continue
        state._job_registry[job_id] = {
            "name": f"{prefix}: {summary}"[:120],
            "kind": "once", "cron": "", "interval": "",
            "run_at": dt.isoformat(),
            "delivery": deliv,
            "misfire_policy": "skip",
            "misfire_grace": state.DEFAULT_MISFIRE_GRACE,
            "fire_if_missed": True,  # calendar events: fire if missed within grace
            "status": "scheduled",
            "last_fired_at": "",
            "created_at": n.isoformat(),
            "source": f"calendar:{url[:80]}",
        }
        jobs_created.append(job_id)

    state._save_jobs()

    return ok({
        "action_status": "synced", "action": "sync_calendar",
        "calendar_url": url,
        "events_found": len(events),
        "events_scheduled": len(jobs_created),
        "events_skipped_past": skipped_past,
        "rrule_skipped": rrule_skipped,
        "parse_errors": parse_errors,
        "jobs": jobs_created,
        "trace_id": trace_id,
    }, trace_id=trace_id)
