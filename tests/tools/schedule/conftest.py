"""Shared fixtures for schedule tool tests.

All schedule infrastructure is mocked — no real APScheduler jobs, no real
notify deliveries, no real files in the user's agent_root. Mirrors
notify_ops's conftest pattern.

Patches:
  - tools.schedule_ops.state.cfg            — agent_root → tmp_path (persistence isolation)
  - core.time_utils.get_timezone            — deterministic America/Sao_Paulo
  - tools.schedule_ops.helpers._get_scheduler — MagicMock scheduler (or None)
  - tools.notify.notify                     — fake successful delivery
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest


# ── Autouse state reset ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_schedule_state():
    """Clear all module-level state in schedule_ops.state before AND after each test."""
    from tools.schedule_ops import state
    state.reset_state()
    yield
    state.reset_state()


# ── cfg + timezone ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_cfg(tmp_path):
    """Patch cfg as seen by schedule_ops.state — agent_root → tmp_path.

    Also pins the timezone via core.time_utils.get_timezone so tests are
    deterministic regardless of host tz.
    """
    mock = MagicMock()
    mock.agent_root = str(tmp_path)
    mock.timezone = "America/Sao_Paulo"
    tz = ZoneInfo("America/Sao_Paulo")
    with patch("tools.schedule_ops.state.cfg", mock), \
         patch("core.time_utils.get_timezone", return_value=tz):
        yield mock


# ── APScheduler ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_scheduler():
    """Patch _get_scheduler to return a MagicMock scheduler."""
    sched = MagicMock()
    sched.get_jobs.return_value = []
    with patch("tools.schedule_ops.helpers._get_scheduler", return_value=sched):
        yield sched


@pytest.fixture
def mock_scheduler_none():
    """Patch _get_scheduler to return None (simulates APScheduler not installed)."""
    with patch("tools.schedule_ops.helpers._get_scheduler", return_value=None):
        yield None


# ── notify delivery backend ──────────────────────────────────────────────────

@pytest.fixture
def mock_notify():
    """Patch tools.notify.notify so deliveries appear to succeed.

    _call_notify does `from tools.notify import notify` at call time, so
    patching the module attribute works.
    """
    with patch("tools.notify.notify", return_value={"status": "success", "data": {"action_status": "sent"}}) as m:
        yield m
