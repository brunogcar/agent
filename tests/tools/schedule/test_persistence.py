"""Persistence: save/load/reload round-trip + atomic write + path."""
from __future__ import annotations

from pathlib import Path

from tools.schedule import schedule
from tools.schedule_ops import state


def test_jobs_path_at_agent_root(mock_cfg, tmp_path):
    p = state._jobs_path()
    assert str(tmp_path) in str(p)
    assert p.name == "jobs.json"
    assert p.parent.name == ".schedule_jobs"


def test_save_creates_file(mock_cfg, mock_scheduler, tmp_path):
    schedule(action="add_cron", cron="0 9 * * *", message="a")
    assert state._jobs_path().exists()


def test_atomic_write_no_tmp_left(mock_cfg, mock_scheduler):
    schedule(action="add_cron", cron="0 9 * * *", message="a")
    files = list(state._jobs_path().parent.iterdir())
    names = [f.name for f in files]
    assert "jobs.json" in names
    assert not any(n.endswith(".tmp") for n in names)


def test_load_round_trip(mock_cfg, mock_scheduler):
    """Save a job, clear registry, reload — job is restored."""
    r = schedule(action="add_cron", cron="0 9 * * 1", name="weekly", message="m")
    jid = r["data"]["job_id"]
    # Clear + reload.
    state._job_registry.clear()
    assert len(state._job_registry) == 0
    state._load_jobs()
    assert jid in state._job_registry
    meta = state._job_registry[jid]
    assert meta["cron"] == "0 9 * * 1"
    assert meta["name"] == "weekly"
    assert meta["kind"] == "cron"


def test_load_missing_file_noop(mock_cfg, tmp_path):
    """No file → _load_jobs is a no-op (first run)."""
    assert not state._jobs_path().exists()
    state._load_jobs()  # must not raise
    assert state._job_registry == {}


def test_load_corrupt_json_noop(mock_cfg, tmp_path):
    """Corrupt JSON → _load_jobs swallows + logs, no crash."""
    p = state._jobs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    state._load_jobs()  # must not raise
    assert state._job_registry == {}


def test_mark_fired_persists(mock_cfg, mock_scheduler):
    r = schedule(action="add_cron", cron="0 9 * * *", message="a")
    jid = r["data"]["job_id"]
    assert state._job_registry[jid]["last_fired_at"] == ""
    state.mark_fired(jid)
    assert state._job_registry[jid]["last_fired_at"] != ""
    # Persisted to disk.
    state._job_registry.clear()
    state._load_jobs()
    assert state._job_registry[jid]["last_fired_at"] != ""
