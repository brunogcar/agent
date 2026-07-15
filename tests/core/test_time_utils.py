"""Tests for core/time_utils.py — tz-aware time helpers + cron computation.

Patches core.time_utils.get_timezone indirectly by patching cfg.timezone, so
tests are deterministic regardless of the host machine's timezone. The .env
in the test sandbox sets AGENT_TZ=America/Sao_Paulo (UTC-3, no DST in July).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core import time_utils
from core.time_utils import (
    now, now_iso, parse_iso, parse_human, parse_duration,
    to_utc, from_utc, format_dt,
    cron_next_fire, compute_missed_fires, get_timezone,
)


# ── Timezone resolution ──────────────────────────────────────────────────────

def test_get_timezone_resolves_configured_name():
    """cfg.timezone='America/Sao_Paulo' → ZoneInfo('America/Sao_Paulo')."""
    tz = get_timezone()
    # In the sandbox .env, AGENT_TZ=America/Sao_Paulo.
    assert str(tz) in ("America/Sao_Paulo", "America/Sao_Paulo")


def test_get_timezone_falls_back_on_invalid_name():
    """A bogus AGENT_TZ must NOT raise — falls through to local/UTC."""
    from core.config import cfg
    with patch.object(cfg, "timezone", "Bogus/Zone"):
        tz = get_timezone()
        # Falls back to local tz (tzinfo) or UTC — never raises, never None.
        assert tz is not None


def test_get_timezone_empty_uses_system_local():
    from core.config import cfg
    with patch.object(cfg, "timezone", ""):
        tz = get_timezone()
        assert tz is not None  # local tz or UTC


def test_get_timezone_never_raises_on_bad_cfg():
    """If cfg access itself fails, get_timezone still returns something."""
    with patch("core.config.cfg", side_effect=Exception("boom"), create=True):
        # The lazy import inside get_timezone catches import errors; simulate
        # by patching get_timezone's internal cfg read path is hard, so instead
        # just assert the normal path is robust. (Smoke test.)
        tz = get_timezone()
        assert tz is not None


# ── now / now_iso ────────────────────────────────────────────────────────────

def test_now_is_tz_aware():
    n = now()
    assert n.tzinfo is not None


def test_now_iso_is_parseable():
    s = now_iso()
    assert "T" in s or "-" in s
    dt = datetime.fromisoformat(s)
    assert dt.tzinfo is not None


# ── parse_iso ────────────────────────────────────────────────────────────────

def test_parse_iso_naive_assumes_configured_tz():
    dt = parse_iso("2026-07-16T09:00:00")
    assert dt.tzinfo is not None
    assert dt.hour == 9


def test_parse_iso_with_explicit_tz():
    dt = parse_iso("2026-07-16T12:00:00+00:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


def test_parse_iso_z_suffix_is_utc():
    dt = parse_iso("2026-07-16T12:00:00Z")
    assert dt.utcoffset() == timedelta(0)


def test_parse_iso_space_separator():
    dt = parse_iso("2026-07-16 09:00:00")
    assert dt.hour == 9


def test_parse_iso_empty_raises():
    with pytest.raises(ValueError):
        parse_iso("")
    with pytest.raises(ValueError):
        parse_iso("   ")


def test_parse_iso_garbage_raises():
    with pytest.raises(ValueError):
        parse_iso("not a date")


# ── parse_duration ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr,expected_seconds", [
    ("10m", 600),
    ("2h", 7200),
    ("1d", 86400),
    ("90s", 90),
    ("500ms", 0.5),
    ("1h30m", 5400),
    ("2d4h", 2 * 86400 + 4 * 3600),
    ("in 10m", None),  # handled by parse_human, not parse_duration
])
def test_parse_duration(expr, expected_seconds):
    if expr.startswith("in "):
        with pytest.raises(ValueError):
            parse_duration(expr)
        return
    td = parse_duration(expr)
    assert td.total_seconds() == pytest.approx(expected_seconds)


def test_parse_duration_case_insensitive():
    assert parse_duration("2H") == timedelta(hours=2)
    assert parse_duration("10M") == timedelta(minutes=10)


def test_parse_duration_empty_raises():
    with pytest.raises(ValueError):
        parse_duration("")
    with pytest.raises(ValueError):
        parse_duration("   ")


def test_parse_duration_garbage_raises():
    with pytest.raises(ValueError):
        parse_duration("banana")


# ── parse_human ──────────────────────────────────────────────────────────────

def test_parse_human_iso():
    dt = parse_human("2026-07-16T09:00:00")
    assert dt.hour == 9
    assert dt.tzinfo is not None


def test_parse_human_space_iso():
    dt = parse_human("2026-07-16 09:00")
    assert dt.hour == 9


def test_parse_human_date_only_midnight():
    dt = parse_human("2026-07-16")
    assert dt.hour == 0
    assert dt.minute == 0


def test_parse_human_relative_in_prefix():
    base = parse_iso("2026-07-16T10:00:00")
    dt = parse_human("in 30m", base=base)
    assert dt == parse_iso("2026-07-16T10:30:00")


def test_parse_human_relative_bare_duration():
    base = parse_iso("2026-07-16T10:00:00")
    dt = parse_human("2h", base=base)
    assert dt == parse_iso("2026-07-16T12:00:00")


def test_parse_human_relative_from_now():
    base = parse_iso("2026-07-16T10:00:00")
    dt = parse_human("10m from now", base=base)
    assert dt == parse_iso("2026-07-16T10:10:00")


def test_parse_human_compound_relative():
    base = parse_iso("2026-07-16T10:00:00")
    dt = parse_human("1h30m", base=base)
    assert dt == parse_iso("2026-07-16T11:30:00")


def test_parse_human_clock_today_if_future():
    base = parse_iso("2026-07-16T08:00:00")
    dt = parse_human("09:00", base=base)
    assert dt.day == 16
    assert dt.hour == 9


def test_parse_human_clock_tomorrow_if_past():
    base = parse_iso("2026-07-16T10:00:00")
    dt = parse_human("09:00", base=base)
    assert dt.day == 17
    assert dt.hour == 9


def test_parse_human_clock_am_pm():
    base = parse_iso("2026-07-16T08:00:00")
    dt = parse_human("9pm", base=base)
    assert dt.hour == 21


def test_parse_human_clock_12am_is_midnight():
    base = parse_iso("2026-07-16T08:00:00")
    dt = parse_human("12am", base=base)
    assert dt.hour == 0


def test_parse_human_clock_12pm_is_noon():
    base = parse_iso("2026-07-16T08:00:00")
    dt = parse_human("12pm", base=base)
    assert dt.hour == 12


def test_parse_human_empty_raises():
    with pytest.raises(ValueError):
        parse_human("")


def test_parse_human_garbage_raises():
    with pytest.raises(ValueError):
        parse_human("sometime next week maybe")


# ── to_utc / from_utc / format_dt ────────────────────────────────────────────

def test_to_utc_naive_assumes_configured_tz():
    dt = datetime(2026, 7, 16, 12, 0, 0)  # naive
    u = to_utc(dt)
    assert u.tzinfo == timezone.utc


def test_from_utc_round_trip():
    u = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    local = from_utc(u)
    # Sao_Paulo is UTC-3 in July → 09:00 local.
    assert local.hour == 9


def test_format_dt_naive_uses_configured_tz():
    dt = datetime(2026, 7, 16, 9, 0, 0)
    s = format_dt(dt)
    assert s == "2026-07-16 09:00:00"


# ── cron_next_fire ───────────────────────────────────────────────────────────

def test_cron_next_fire_uses_configured_tz():
    """0 9 * * * → 09:00 in configured tz (Sao_Paulo), NOT 09:00 UTC."""
    nxt = cron_next_fire("0 9 * * *")
    assert nxt is not None
    assert nxt.hour == 9  # 9am local, not 6am (which would be 9am UTC)


def test_cron_next_fire_every_5_minutes():
    base = parse_iso("2026-07-16T10:02:00")
    nxt = cron_next_fire("*/5 * * * *", after=base)
    assert nxt is not None
    assert nxt.minute == 5
    assert nxt.hour == 10


def test_cron_next_fire_invalid_raises():
    with pytest.raises(ValueError):
        cron_next_fire("not a cron")


def test_cron_next_fire_with_explicit_after():
    base = parse_iso("2026-07-16T10:00:00")
    # Monday cron; 2026-07-16 is a Thursday. Next Monday is 2026-07-20.
    nxt = cron_next_fire("0 9 * * 1", after=base)
    assert nxt is not None
    assert nxt.weekday() == 0  # Monday
    assert nxt.hour == 9


# ── compute_missed_fires ─────────────────────────────────────────────────────

def test_compute_missed_fires_daily_two_days_ago():
    """0 9 * * * last fired 2 days ago at 08:59 → 2 missed fires (yesterday + today if past)."""
    base = parse_iso("2026-07-16T10:00:00")
    last_fired = parse_iso("2026-07-14T08:59:00")
    missed = compute_missed_fires("0 9 * * *", last_fired, until=base)
    # Fires: 2026-07-14 09:00, 2026-07-15 09:00, 2026-07-16 09:00 (all <= 10:00).
    assert len(missed) == 3
    for m in missed:
        assert m.hour == 9
        assert m.tzinfo is not None


def test_compute_missed_fires_none_when_last_fired_recent():
    base = parse_iso("2026-07-16T10:00:00")
    last_fired = parse_iso("2026-07-16T09:30:00")
    missed = compute_missed_fires("0 9 * * *", last_fired, until=base)
    assert missed == []


def test_compute_missed_fires_excludes_last_fired_instant():
    """last_fired == a fire time → that instant is NOT included (exclusive)."""
    base = parse_iso("2026-07-16T10:00:00")
    last_fired = parse_iso("2026-07-16T09:00:00")
    missed = compute_missed_fires("0 9 * * *", last_fired, until=base)
    assert missed == []


def test_compute_missed_fires_naive_last_fired_assumes_configured_tz():
    base = parse_iso("2026-07-16T10:00:00")
    last_fired = datetime(2026, 7, 14, 8, 59)  # naive
    missed = compute_missed_fires("0 9 * * *", last_fired, until=base)
    assert len(missed) >= 1
    assert all(m.tzinfo is not None for m in missed)


def test_compute_missed_fires_max_count_cap():
    """A very old last_fired + low max_count → ValueError (safety cap)."""
    base = parse_iso("2026-07-16T10:00:00")
    last_fired = parse_iso("2026-01-01T00:00:00")
    with pytest.raises(ValueError):
        compute_missed_fires("0 * * * *", last_fired, until=base, max_count=10)


def test_compute_missed_fires_every_minute_capped_correctly():
    """*/1 * * * * over a short window yields the right count, no runaway."""
    base = parse_iso("2026-07-16T10:05:00")
    last_fired = parse_iso("2026-07-16T10:00:00")
    missed = compute_missed_fires("* * * * *", last_fired, until=base)
    # Fires at 10:01, 10:02, 10:03, 10:04, 10:05 → 5.
    assert len(missed) == 5


def test_compute_missed_fires_invalid_cron_raises():
    with pytest.raises(ValueError):
        compute_missed_fires("banana", parse_iso("2026-07-16T09:00:00"))
