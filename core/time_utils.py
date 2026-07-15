"""core/time_utils.py — Single source of truth for time/timezone in the agent.

Provides tz-aware datetime helpers, ISO parsing, human-relative parsing
("in 10m", "tomorrow 9am"), duration parsing, cron next-fire computation,
and missed-fire computation for catch-up on startup.

WHY THIS EXISTS (v1.0):
  - ``notify`` previously used naive ``datetime.now()`` everywhere — breaks
    silently if the host timezone changes or DST transitions occur.
  - The new ``schedule`` tool needs cron next-fire + missed-fire computation
    to support catch-up of jobs that were due while the server was offline.
  - Both need a single timezone source (``cfg.timezone``) instead of ad-hoc
    ``os.getenv`` scattered across tools.
  - Replaces the external ``@mcpcentral/mcp-time`` MCP dependency for our OWN
    tooling (that MCP server remains configured for LLM-side time queries if
    desired, but our tools no longer depend on it).

DESIGN DECISIONS:
  1. ALWAYS tz-aware. ``now()`` returns a tz-aware datetime in the configured
     timezone. ``parse_iso()`` assumes the configured tz if the input is naive.
     Never returns naive datetimes — naive datetimes are the root cause of the
     subtle DST/tz bugs this module exists to prevent.

  2. NO hard dependency on ``tzlocal`` (not installed in all envs). Local tz
     is resolved via ``datetime.now().astimezone().tzinfo`` (stdlib, always
     works) when ``cfg.timezone`` is empty. ``zoneinfo`` (stdlib, Py 3.9+) is
     used for named timezones.

  3. LAZY cfg access. ``get_timezone()`` reads ``cfg.timezone`` at CALL time,
     not at module import — so tests can patch ``cfg`` and so import order
     never matters (``core.config`` construction is heavy).

  4. APScheduler is a SOFT dependency. Only ``cron_next_fire`` /
     ``compute_missed_fires`` need it (they wrap ``CronTrigger``). Everything
     else is pure stdlib. Callers that don't need cron logic pay zero import
     cost for APScheduler.

  5. ``compute_missed_fires`` is capped (default 1000) to prevent runaway
     iteration if ``last_fired`` is far in the past (e.g. server offline for
     months). The cap is the caller's safety net — ``catch_up_missed_jobs``
     also applies a grace window before firing.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional, List

# ── Timezone resolution ──────────────────────────────────────────────────────

def get_timezone() -> tzinfo:
    """Return the agent's configured timezone as a tzinfo object.

    Resolution order:
      1. ``cfg.timezone`` (env ``AGENT_TZ``) → ``ZoneInfo(name)`` if set.
      2. System local timezone via ``datetime.now().astimezone().tzinfo``
         (stdlib, always available — does NOT require tzlocal).
      3. UTC (final fallback, never raises).

    Lazy ``cfg`` access: reads at call time so import order and test patches
    both work. Never raises — a bad ``AGENT_TZ`` value falls through to local
    then UTC with a stderr warning.
    """
    # Step 1: configured named timezone.
    try:
        from core.config import cfg
        tz_name = (getattr(cfg, "timezone", "") or "").strip()
    except Exception:
        tz_name = ""

    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tz_name)
        except Exception as e:
            import sys
            print(f"[time_utils.get_timezone] WARNING: invalid AGENT_TZ "
                  f"{tz_name!r}: {e}; falling back to local/UTC", file=sys.stderr)

    # Step 2: system local timezone (stdlib — no tzlocal dependency).
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            return local_tz
    except Exception:
        pass

    # Step 3: UTC.
    return timezone.utc


def now() -> datetime:
    """Current time as a tz-aware datetime in the configured timezone."""
    return datetime.now(tz=get_timezone())


def now_iso() -> str:
    """Current time as an ISO 8601 string (tz-aware)."""
    return now().isoformat()


# ── Parsing ──────────────────────────────────────────────────────────────────

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?")
_DATEONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_TIME_AMPM_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)\s*$",
    re.IGNORECASE,
)
_RELATIVE_RE = re.compile(
    r"^\s*(?:in\s+)?(\d+(?:\.\d+)?\s*(?:ms|s|m|h|d|w))\s*(?:from\s+now)?\s*$",
    re.IGNORECASE,
)

_DURATION_UNITS = {
    "ms": timedelta(milliseconds=1),
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}


def parse_duration(s: str) -> timedelta:
    """Parse a duration string into a timedelta.

    Supports compound forms like "1h30m", "2d4h", "10m", "90s", "500ms".
    Unit suffixes (case-insensitive): ms, s, m, h, d, w.

    Raises ValueError on unparseable input (never returns a silent 0).
    """
    if not s or not s.strip():
        raise ValueError("empty duration string")
    s = s.strip().lower()
    # Try single-unit fast path first.
    m = _DURATION_RE.match(s)
    if m:
        return float(m.group(1)) * _DURATION_UNITS[m.group(2).lower()]
    # Compound: "1h30m", "2d4h" — scan greedily.
    total = timedelta()
    pos = 0
    matched_any = False
    compound = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)", re.IGNORECASE)
    while pos < len(s):
        cm = compound.match(s, pos)
        if not cm:
            break
        total += float(cm.group(1)) * _DURATION_UNITS[cm.group(2).lower()]
        pos = cm.end()
        matched_any = True
    if matched_any and pos == len(s):
        return total
    raise ValueError(f"unparseable duration: {s!r}")


def parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 string into a tz-aware datetime.

    Naive inputs are assumed to be in the configured timezone (so a stored
    "2026-07-16T09:00:00" without tz suffix is interpreted as local time).
    Trailing 'Z' is treated as UTC. Handles both 'T' and space separators,
    with or without seconds/microseconds.
    """
    if not s or not s.strip():
        raise ValueError("empty datetime string")
    s = s.strip()
    # Trailing Z = UTC.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"unparseable ISO datetime: {s!r}: {e}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_timezone())
    return dt


def parse_human(s: str, base: Optional[datetime] = None) -> datetime:
    """Parse a human-friendly time string into a tz-aware datetime.

    Supported forms (all return tz-aware datetimes):
      - ISO 8601:        "2026-07-16T09:00:00", "2026-07-16 09:00"
      - Date only:       "2026-07-16"  (midnight in configured tz)
      - Clock time:      "09:00", "9:30", "21:30", "9am", "9:30pm"
                         (today if still future, else tomorrow)
      - Relative:        "in 10m", "in 2h", "10m", "2h", "1d", "1h30m from now"

    ``base`` defaults to ``now()``; relative/clock forms resolve against it.

    Raises ValueError on unparseable input. This is a deliberately small,
    dependency-free parser — it does NOT do full NLP. For anything it cannot
    parse, callers should fall back to passing an ISO string.
    """
    if not s or not s.strip():
        raise ValueError("empty time string")
    raw = s.strip()
    base = base or now()

    # ISO 8601 (with time).
    if _ISO_RE.match(raw):
        return parse_iso(raw)

    # Date only → midnight in configured tz.
    if _DATEONLY_RE.match(raw):
        return parse_iso(raw + "T00:00:00")

    # Relative: "in 10m", "10m", "2h from now", "1h30m", "in 1h30m from now".
    # Strip optional "in " prefix and " from now" suffix, then attempt a
    # duration parse (handles both single-unit "10m" and compound "1h30m").
    stripped = raw
    had_in = False
    if stripped.lower().startswith("in "):
        stripped = stripped[3:].strip()
        had_in = True
    if stripped.lower().endswith(" from now"):
        stripped = stripped[:-len(" from now")].strip()
    try:
        dur = parse_duration(stripped)
        return base + dur
    except ValueError:
        if had_in:
            # "in <garbage>" is unambiguously intended as relative → hard error.
            raise ValueError(f"unparseable time: {s!r}")
        # else: not a duration → fall through to clock-time parsing below.

    # Clock time "HH:MM[:SS]" — today if future, else tomorrow.
    tm = _TIME_RE.match(raw)
    if tm:
        h, mi, sec = int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)
        return _clock_today_or_tomorrow(base, h, mi, sec)

    # Clock time "9am" / "9:30pm".
    am = _TIME_AMPM_RE.match(raw)
    if am:
        h = int(am.group(1))
        mi = int(am.group(2) or 0)
        suffix = am.group(3).lower()
        if suffix == "pm" and h != 12:
            h += 12
        elif suffix == "am" and h == 12:
            h = 0
        return _clock_today_or_tomorrow(base, h, mi, 0)

    raise ValueError(f"unparseable time: {s!r}")


def _clock_today_or_tomorrow(base: datetime, h: int, mi: int, sec: int) -> datetime:
    """Return today's h:mi:sec if it's still in the future, else tomorrow's."""
    candidate = base.replace(hour=h, minute=mi, second=sec, microsecond=0)
    if candidate <= base:
        candidate += timedelta(days=1)
    return candidate


# ── Conversion / formatting ──────────────────────────────────────────────────

def to_utc(dt: datetime) -> datetime:
    """Convert a datetime to UTC. Naive inputs assumed to be in configured tz."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_timezone())
    return dt.astimezone(timezone.utc)


def from_utc(dt: datetime, tz: Optional[tzinfo] = None) -> datetime:
    """Convert a UTC datetime to the given tz (default: configured tz)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz or get_timezone())


def format_dt(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime. Naive inputs assumed to be in configured tz."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_timezone())
    return dt.strftime(fmt)


# ── Cron helpers (soft APScheduler dependency) ───────────────────────────────

# Crontab day-of-week is 0=Sunday (vixie-cron). APScheduler's CronTrigger
# treats numeric day_of_week as 0=Monday — a subtle off-by-one trap. We remap
# the crontab DOW field to unambiguous day NAMES (sun/mon/...) so standard
# cron semantics are preserved regardless of APScheduler's numeric convention.
_DOW_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]  # index = crontab day (0=Sun)
_DOW_NAME_TO_NUM = {name: i for i, name in enumerate(_DOW_NAMES)}


def _dow_to_num(token: str) -> int:
    """Resolve a single DOW token (name or 0-7, 0/7=Sunday) to 0-6 (0=Sun)."""
    t = token.strip().lower()
    if t in _DOW_NAME_TO_NUM:
        return _DOW_NAME_TO_NUM[t]
    try:
        n = int(t)
    except ValueError as e:
        raise ValueError(f"invalid day-of-week token: {token!r}") from e
    if n == 7:
        n = 0
    if n < 0 or n > 6:
        raise ValueError(f"day-of-week out of range 0-7: {token!r}")
    return n


def _crontab_dow_to_aps(field: str) -> str:
    """Convert a crontab DOW field to an APScheduler day_of_week names string.

    Handles: ``*``, ``*/N``, ``a-b``, ``a-b/N``, ``a,b,c``, names (sun/mon/...),
    and any combination. Returns a comma-joined list of unambiguous day names
    (e.g. ``"mon,tue,wed,thu,fri"``) so APScheduler interprets them correctly
    regardless of its numeric 0=Monday convention.
    """
    field = field.strip().lower()
    if not field:
        raise ValueError("empty day-of-week field")
    days: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        base = part
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError as e:
                raise ValueError(f"invalid DOW step: {step_s!r}") from e
            if step <= 0:
                raise ValueError(f"DOW step must be > 0: {step_s!r}")
        if base == "*":
            lo, hi = 0, 6
        elif "-" in base:
            a, b = base.split("-", 1)
            lo = _dow_to_num(a)
            hi = _dow_to_num(b)
        else:
            lo = hi = _dow_to_num(base)
        d = lo
        # Expand lo..hi with step. No wrap-around (cron ranges don't wrap).
        while d <= hi:
            days.add(d % 7)
            d += step
    if not days:
        raise ValueError(f"empty DOW expansion for {field!r}")
    return ",".join(_DOW_NAMES[d] for d in sorted(days))


def _build_cron_trigger(cron_expr: str, tz: tzinfo):
    """Build an APScheduler CronTrigger from a 5-field crontab expression.

    The DOW field is remapped to day-names via ``_crontab_dow_to_aps`` so
    standard cron (0=Sunday) semantics are preserved. The other fields
    (minute/hour/day/month) use the same numeric convention in crontab and
    APScheduler, so they pass through unchanged.

    Raises ValueError on invalid expressions (field count, bad DOW, etc.).
    """
    import re as _re
    from apscheduler.triggers.cron import CronTrigger
    fields = _re.split(r"\s+", cron_expr.strip())
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have 5 fields (minute hour day month dow), "
            f"got {len(fields)}: {cron_expr!r}"
        )
    minute, hour, day, month, dow = fields
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month,
        day_of_week=_crontab_dow_to_aps(dow),
        timezone=tz,
    )


def cron_next_fire(cron_expr: str, after: Optional[datetime] = None) -> Optional[datetime]:
    """Compute the next fire time of a 5-field cron expression after ``after``.

    ``after`` defaults to ``now()``. Returns None if the expression never
    fires again (rare). The cron fields are interpreted in the agent's
    CONFIGURED timezone (``cfg.timezone``) — so ``"0 9 * * *"`` means 09:00
    in ``America/Sao_Paulo``, NOT 09:00 UTC. Wraps APScheduler's
    ``CronTrigger.from_crontab(expr, timezone=...)``.

    Raises ValueError on invalid cron expressions (re-raised from APScheduler).
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as e:
        raise RuntimeError(
            "APScheduler not installed — cron helpers unavailable. "
            "Run: pip install apscheduler"
        ) from e
    tz = get_timezone()
    trigger = _build_cron_trigger(cron_expr, tz)
    after = after or now()
    if after.tzinfo is None:
        after = after.replace(tzinfo=tz)
    nxt = trigger.get_next_fire_time(None, after)
    if nxt is None:
        return None
    # APScheduler returns tz-aware in the trigger's tz (== configured tz).
    return nxt.astimezone(tz)


def compute_missed_fires(
    cron_expr: str,
    last_fired: datetime,
    until: Optional[datetime] = None,
    max_count: int = 1000,
) -> List[datetime]:
    """Compute the list of cron fire times in ``(last_fired, until]``.

    Used by ``schedule_ops.state.catch_up_missed_jobs`` to determine which
    recurring jobs should have fired while the server was offline. All returned
    datetimes are tz-aware in the configured timezone.

    Args:
        cron_expr: 5-field cron expression.
        last_fired: tz-aware datetime of the last successful fire (exclusive
                    lower bound). If naive, assumed configured tz.
        until:      tz-aware upper bound (inclusive). Defaults to ``now()``.
        max_count:  Safety cap to prevent runaway iteration if ``last_fired``
                    is far in the past. Raises ValueError if exceeded.

    Returns the ordered list of fire times > last_fired and <= until. Empty
    list if none. ``last_fired`` itself is never included (exclusive).
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as e:
        raise RuntimeError(
            "APScheduler not installed — cron helpers unavailable. "
            "Run: pip install apscheduler"
        ) from e

    tz = get_timezone()
    if last_fired.tzinfo is None:
        last_fired = last_fired.replace(tzinfo=tz)
    until = until or now()
    if until.tzinfo is None:
        until = until.replace(tzinfo=tz)

    # Interpret cron fields in the CONFIGURED timezone (not system-local),
    # with standard crontab DOW semantics (0=Sunday) via _build_cron_trigger.
    trigger = _build_cron_trigger(cron_expr, tz)
    # EXCLUSIVE lower bound: pass previous=last_fired so the first fire
    # returned is strictly AFTER last_fired (get_next_fire_time(None, now)
    # is inclusive of `now`, which would re-include the last-fired instant).
    prev = last_fired
    end = until
    missed: List[datetime] = []
    while True:
        # APScheduler trap: get_next_fire_time(prev, now) IGNORES prev and
        # returns the first fire >= now whenever now < prev. Passing prev as
        # BOTH previous and now (Variant B) yields the first fire strictly
        # after prev — the correct advancing + exclusive semantics we need.
        nxt = trigger.get_next_fire_time(prev, prev)
        if nxt is None or nxt > end:
            break
        missed.append(nxt.astimezone(tz))
        prev = nxt
        if len(missed) >= max_count:
            raise ValueError(
                f"compute_missed_fires exceeded max_count={max_count} for "
                f"cron {cron_expr!r}; last_fired={last_fired!r} is too far "
                f"in the past. Apply a grace window before calling."
            )
    return missed
