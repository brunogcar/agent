"""Shared fixtures for python tool tests.

Patches four modules so action handlers can be tested in isolation:
  - tools.python_ops.executors.cfg            — workspace_root + execution_timeout
  - tools.python_ops.actions.run.prune_text   — passthrough (no artifact writes)
  - tools.python_ops.actions.run_data.prune_text — passthrough (no artifact writes)
  - core.tracer.tracer                        — no-op step() (avoid trace store I/O)

Mirrors tests/tools/consult/conftest.py structure. Default fixtures:
  - mock_cfg: workspace_root=/tmp, execution_timeout=10. Use mutate-then-yield
    pattern in tests that need different values.
  - mock_pruner: prune_text passes text through unchanged (no truncation, no
    artifact writes).
  - temp_workspace: yields a real tmpdir; tests that exercise _run_subprocess
    can mutate mock_cfg.workspace_root to point here.

Note on patch targets: prune_text is imported via `from X import prune_text`
at the top of run.py / run_data.py. Import-time-binding means patching the
original `core.memory_backend.pruner.prune_text` would NOT affect the local
binding — we must patch each action module's `prune_text` attribute directly.
This is the same lesson learned in consult-v1.0-code (see Anti-Pattern #1 in
docs/tools/consult/INSTRUCTIONS.md).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_cfg():
    """Patch the cfg singleton as seen by tools.python_ops.executors.

    Default: workspace_root=/tmp (exists on all platforms), execution_timeout=10s.
    Tests can mutate `mock.workspace_root` to point at temp_workspace.
    """
    with patch("tools.python_ops.executors.cfg") as mock:
        mock.workspace_root = Path("/tmp")
        mock.execution_timeout = 10
        yield mock


@pytest.fixture
def mock_pruner():
    """Patch prune_text in BOTH run and run_data action modules.

    prune_text is imported at module load time via `from X import prune_text`,
    so the binding in each action module is independent. We patch each one.

    Default behavior: passthrough (return text unchanged). Tests that need
    to verify truncation behavior can override the return_value.
    """
    def _passthrough(tool_name, text, trace_id):
        return text

    with patch("tools.python_ops.actions.run.prune_text", side_effect=_passthrough) as run_mock, \
         patch("tools.python_ops.actions.run_data.prune_text", side_effect=_passthrough) as rd_mock:
        yield {"run": run_mock, "run_data": rd_mock}


@pytest.fixture
def temp_workspace():
    """Yield a real temporary directory for subprocess tests.

    Use this when a test needs _run_subprocess to actually write a temp .py
    file. Bind it to mock_cfg.workspace_root in the test:
        def test_x(mock_cfg, temp_workspace):
            mock_cfg.workspace_root = temp_workspace
            ...
    """
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_tracer():
    """Patch core.tracer.tracer.step to a no-op.

    The real tracer writes to a trace store; for tests we want zero side
    effects. Patches `core.tracer.tracer` as seen by tools.python (the
    facade imports `from core.tracer import tracer`).
    """
    with patch("core.tracer.tracer") as mock:
        mock.step = MagicMock()
        yield mock


def make_subprocess_result(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a fake subprocess.CompletedProcess for testing subprocess paths."""
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)
