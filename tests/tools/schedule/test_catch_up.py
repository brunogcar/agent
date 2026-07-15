"""Offline missed-fire recovery — the key schedule feature."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from core.time_utils import now, parse_iso
from tools.schedule_ops import state
from tools.schedule_ops.state import catch_up_missed_jobs


def _make_cron_job(job_id, last_fired_iso, policy="fire_last", grace="24h"):
    """Insert a registry entry directly (simulating loaded-from-disk state)."""
    state._job_registry[job_id] = {
        "name": "test", "kind": "cron", "cron": "0 9 * * *", "interval": "",
        "run_at": "", "delivery": {"tool": "notify", "action": "send", "title": "T", "message": "M"},
        "misfire_policy": policy, "misfire_grace": grace, "fire_if_missed": False,
        "status": "recurring", "last_fired_at": last_fired_iso,
        "created_at": last_fired_iso, "source": "manual",
    }


def test_catch_up_fire_last(mock_cfg, mock_notify):
    """Cron job missed 2 daily fires → fire_last delivers ONCE (most recent)."""
    n = now()
    last = (n - timedelta(days=2)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last")
    summary = catch_up_missed_jobs(force=True)
    assert summary["jobs_with_misses"] == 1
    assert summary["fires_delivered"] == 1  # fire_last → 1
    assert mock_notify.call_count == 1
    # last_fired_at advanced (idempotent).
    assert state._job_registry["cron_x"]["last_fired_at"] != ""


def test_catch_up_skip(mock_cfg, mock_notify):
    """policy=skip → 0 deliveries, but last_fired_at still advanced (idempotent)."""
    n = now()
    last = (n - timedelta(days=2)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="skip")
    summary = catch_up_missed_jobs(force=True)
    assert summary["fires_delivered"] == 0
    assert summary["fires_skipped"] >= 1
    assert mock_notify.call_count == 0
    assert state._job_registry["cron_x"]["last_fired_at"] != ""


def test_catch_up_fire_all(mock_cfg, mock_notify):
    """Interval hourly, missed several → fire_all delivers each (capped)."""
    n = now()
    last = n - timedelta(hours=5, minutes=1)
    state._job_registry["int_x"] = {
        "name": "hb", "kind": "interval", "cron": "", "interval": "1h", "run_at": "",
        "delivery": {"tool": "notify", "action": "send", "title": "T", "message": "M"},
        "misfire_policy": "fire_all", "misfire_grace": "24h", "fire_if_missed": False,
        "status": "recurring", "last_fired_at": last.isoformat(),
        "created_at": last.isoformat(), "source": "manual",
    }
    summary = catch_up_missed_jobs(force=True)
    assert summary["fires_delivered"] >= 4  # ~5 hourly fires
    assert mock_notify.call_count == summary["fires_delivered"]


def test_catch_up_grace_drops_old(mock_cfg, mock_notify):
    """last_fired 30 days ago, grace 24h → all missed fires dropped → 0 deliveries."""
    n = now()
    last = (n - timedelta(days=30)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last", grace="1h")
    summary = catch_up_missed_jobs(force=True)
    assert summary["fires_delivered"] == 0
    assert mock_notify.call_count == 0


def test_catch_up_once_fire_if_missed(mock_cfg, mock_notify):
    """Once-job, run_at in past, fire_if_missed=True, within grace → 1 delivery."""
    n = now()
    past = (n - timedelta(hours=2)).isoformat()
    state._job_registry["once_x"] = {
        "name": "m", "kind": "once", "cron": "", "interval": "",
        "run_at": past, "delivery": {"tool": "notify", "action": "send", "title": "T", "message": "M"},
        "misfire_policy": "skip", "misfire_grace": "24h", "fire_if_missed": True,
        "status": "scheduled", "last_fired_at": "",
        "created_at": (n - timedelta(days=3)).isoformat(), "source": "manual",
    }
    summary = catch_up_missed_jobs(force=True)
    assert summary["fires_delivered"] == 1
    assert mock_notify.call_count == 1
    assert state._job_registry["once_x"]["status"] == "fired"


def test_catch_up_once_no_fire_if_missed(mock_cfg, mock_notify):
    """Once-job, run_at in past, fire_if_missed=False → 0 deliveries."""
    n = now()
    past = (n - timedelta(hours=2)).isoformat()
    state._job_registry["once_x"] = {
        "name": "m", "kind": "once", "cron": "", "interval": "",
        "run_at": past, "delivery": {"tool": "notify", "action": "send", "title": "T", "message": "M"},
        "misfire_policy": "skip", "misfire_grace": "24h", "fire_if_missed": False,
        "status": "scheduled", "last_fired_at": "",
        "created_at": (n - timedelta(days=3)).isoformat(), "source": "manual",
    }
    summary = catch_up_missed_jobs(force=True)
    assert summary["fires_delivered"] == 0
    assert mock_notify.call_count == 0


def test_catch_up_idempotent(mock_cfg, mock_notify):
    """Running catch_up twice (force) → second run delivers 0 (last_fired advanced)."""
    n = now()
    last = (n - timedelta(days=2)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last")
    s1 = catch_up_missed_jobs(force=True)
    assert s1["fires_delivered"] == 1
    s2 = catch_up_missed_jobs(force=True)
    assert s2["fires_delivered"] == 0  # last_fired already advanced


def test_catch_up_guard_once_per_process(mock_cfg, mock_notify):
    """Without force, catch_up runs once; second call returns a note."""
    n = now()
    last = (n - timedelta(days=2)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last")
    s1 = catch_up_missed_jobs(force=False)
    assert s1["fires_delivered"] == 1
    s2 = catch_up_missed_jobs(force=False)
    assert "already run" in s2.get("note", "").lower()


def test_catch_up_cancelled_skipped(mock_cfg, mock_notify):
    n = now()
    last = (n - timedelta(days=2)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last")
    state._job_registry["cron_x"]["status"] = "cancelled"
    summary = catch_up_missed_jobs(force=True)
    assert summary["jobs_with_misses"] == 0
    assert mock_notify.call_count == 0


def test_catch_up_message_stamped(mock_cfg, mock_notify):
    """Catch-up deliveries are stamped '[catch-up for fire @ ...]'."""
    n = now()
    last = (n - timedelta(days=1)).replace(hour=8, minute=59, second=0, microsecond=0)
    _make_cron_job("cron_x", last.isoformat(), policy="fire_last")
    catch_up_missed_jobs(force=True)
    msg = mock_notify.call_args.kwargs.get("message", "")
    assert "catch-up" in msg.lower()
