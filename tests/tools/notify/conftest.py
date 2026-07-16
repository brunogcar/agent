"""Shared fixtures for notify tool tests.

All notify infrastructure is fully mocked — no real desktop notifications
are sent, no real APScheduler jobs are scheduled (except where explicitly
tested), no real files are written to the user's workspace.

Patches four things across two modules so action handlers can be tested in
isolation:
  - tools.notify_ops.helpers.cfg        — is_windows
  - tools.notify_ops.state.cfg          — agent_root (v1.1: for _save_jobs / _load_jobs)
  - tools.notify_ops.helpers._get_scheduler  — return MagicMock instead of real scheduler
  - plyer.notification.notify           — fake Windows toast success
  - subprocess.run                      — fake notify-send success on Linux

The `reset_notify_state` autouse fixture runs before every test and clears
all module-level state (scheduler singleton, job registry, delivery log)
so tests are fully isolated.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Autouse state reset ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_notify_state():
    """Clear all module-level state in notify_ops.state before AND after each test.

    Without this, _job_registry and _delivery_log leak between tests, causing
    order-dependent failures. reset_state() also shuts down any real
    BackgroundScheduler that might have been started.
    """
    # Lazy import so importing conftest doesn't drag in notify_ops (which
    # would trigger @register_action for all actions even when running
    # unrelated test files).
    from tools.notify_ops import state
    state.reset_state()
    yield
    state.reset_state()


# ── cfg singleton ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_cfg(tmp_path):
    """Patch the cfg singleton as seen by BOTH notify_ops.helpers AND notify_ops.state.

    Default: Linux (is_windows=False), agent_root = tmp_path (v1.1: persistence
    moved from workspace_root → agent_root, mirroring .understand/.schedule_jobs).
    Tests can mutate `mock.is_windows = True` to exercise the Windows/plyer path.
    """
    mock = MagicMock()
    mock.is_windows = False
    mock.agent_root = str(tmp_path)

    with patch("tools.notify_ops.helpers.cfg", mock), \
         patch("tools.notify_ops.state.cfg", mock):
        yield mock


# ── APScheduler ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_scheduler():
    """Patch tools.notify_ops.helpers._get_scheduler to return a MagicMock.

    Returns the mock scheduler so tests can configure get_jobs(),
    add_job(), remove_job() return values.

    Note: this patches the helper, not state._scheduler directly, so any
    test that wants to exercise the "scheduler not running" path can use
    mock_scheduler_none instead.
    """
    sched = MagicMock()
    sched.get_jobs.return_value = []
    with patch("tools.notify_ops.helpers._get_scheduler", return_value=sched):
        yield sched


@pytest.fixture
def mock_scheduler_none():
    """Patch _get_scheduler to return None (simulates APScheduler not installed).

    Used to exercise the graceful "APScheduler not installed" / "Scheduler
    not running" error paths in schedule / cancel / list / recurring.
    """
    with patch("tools.notify_ops.helpers._get_scheduler", return_value=None):
        yield None


# ── Desktop notification backends ────────────────────────────────────────────

@pytest.fixture
def mock_plyer():
    """Patch plyer.notification.notify so it appears to succeed silently.

    Used with mock_cfg.is_windows=True to exercise the Windows path.
    Tests can flip side_effect to an Exception to exercise the plyer→console
    fallback chain.
    """
    # plyer may not be installed in the test environment — patch the module
    # path even if it's missing, by ensuring sys.modules has a mock for it.
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"plyer": mock_module, "plyer.notification": mock_module.notification}):
        yield mock_module.notification.notify


@pytest.fixture
def mock_notify_send():
    """Patch subprocess.run so the Linux notify-send path appears to succeed.

    Returns the mock so tests can configure returncode or raise FileNotFoundError
    to exercise the notify-send→console fallback chain.
    """
    success_result = MagicMock()
    success_result.returncode = 0
    with patch("subprocess.run", return_value=success_result) as mock:
        yield mock
