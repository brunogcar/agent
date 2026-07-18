"""tests/core/observability/conftest.py — Shared fixtures for the observability suite.

Scope: tracer_engine, reader, metrics, checkpoint.

Why a conftest?
  The observability subsystem uses module-level singletons that persist across
  tests unless explicitly isolated:

  - ``_TraceStore`` (tracer_engine) — holds the last 200 traces in memory.
    Without isolation, ``tracer.recent()`` returns traces from earlier tests
    and size-based assertions become flaky.
  - ``_FileWriter`` (tracer_engine) — opens real JSONL files under
    ``cfg.agent_log_path`` (``logs/agent/agent_YYYYMMDD.jsonl``). Tests must
    not pollute the developer's log directory.
  - ``CHECKPOINT_DIR`` / ``QUARANTINE_DIR`` (checkpoint) — created at import
    time under ``workspace/checkpoints``. Tests must redirect these to a
    tmp dir so quarantine / scan_incomplete don't touch real journals.
  - ``cfg.log_path`` (reader) — the disk-scan fallback path. Tests redirect
    to tmp so synthetic log files don't collide with real ones.

Fixture summary
  - ``clean_store`` (autouse) — clears the in-memory _TraceStore before+after.
  - ``mock_writer`` — replaces _FileWriter with a MagicMock; assert on writes.
  - ``isolated_tracer`` — bundle of clean_store + mock_writer.
  - ``isolated_log_path`` — redirects cfg.log_path to tmp_path for reader tests.
  - ``isolated_checkpoint_dirs`` — redirects CHECKPOINT_DIR + QUARANTINE_DIR.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tracer engine: isolate the in-memory store (autouse — always runs)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_store():
    """Clear the module-level ``_TraceStore`` before and after each test.

    The store is a process-wide singleton (``tracer_engine._store``). Without
    this fixture, traces created by one test leak into ``tracer.recent()`` in
    subsequent tests, making count-based assertions non-deterministic.

    This is autouse so *every* test in the observability tree gets a clean
    slate, even if it doesn't explicitly request the fixture.
    """
    from core.observability import tracer_engine as te
    store = te._store
    store._store.clear()
    store._order.clear()
    yield store
    store._store.clear()
    store._order.clear()


# ---------------------------------------------------------------------------
# Tracer engine: suppress disk I/O via mock _FileWriter
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_writer():
    """Replace the module-level ``_FileWriter`` with a MagicMock.

    Patches ``core.observability.tracer_engine._writer`` — the canonical
    location. The ``core.tracer`` facade re-exports this name, but the
    ``Tracer`` methods resolve ``_writer`` through the ``tracer_engine``
    module globals at call time, so this single patch target covers both
    the engine singleton and the facade singleton.

    Usage::

        def test_something(mock_writer):
            tracer.new_trace("wf")
            assert mock_writer.write.call_count == 1
            record = mock_writer.write.call_args[0][0]
            assert record["event"] == "trace_start"
    """
    from core.observability import tracer_engine as te
    with patch.object(te, "_writer", MagicMock()) as mock:
        yield mock


@pytest.fixture
def isolated_tracer(clean_store, mock_writer):
    """Convenience bundle: clean store + mocked writer.

    Use for any test that calls ``tracer.new_trace / step / error / warning /
    finish`` so no real I/O occurs and no state leaks between tests.
    """
    from core.observability.tracer_engine import tracer
    return tracer


# ---------------------------------------------------------------------------
# Reader: redirect cfg.log_path to a tmp dir
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_log_path(tmp_path):
    """Redirect ``cfg.agent_log_path`` to ``tmp_path`` for reader disk-scan tests.

    The reader's ``_scan_disk`` function globs ``cfg.agent_log_path`` for
    ``agent_*.jsonl`` files (v1.1 fix — previously globbed cfg.log_path which
    was the wrong directory). This fixture lets a test create synthetic log
    files in isolation, then assert on the reader's output.
    """
    from core.observability import reader
    with patch.object(reader, "cfg") as mock_cfg:
        mock_cfg.agent_log_path = tmp_path
        yield tmp_path


# ---------------------------------------------------------------------------
# Checkpoint: redirect CHECKPOINT_DIR + QUARANTINE_DIR to tmp
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_checkpoint_dirs(tmp_path):
    """Redirect checkpoint module-level dirs to tmp_path.

    ``checkpoint.py`` creates ``CHECKPOINT_DIR`` and ``QUARANTINE_DIR`` at
    import time (``workspace/checkpoints`` and ``workspace/checkpoints/
    quarantine``). Since these are module-level constants, we patch them on
    the module object so ``save_checkpoint``, ``get_latest``, ``quarantine``,
    ``mark_complete``, and ``scan_incomplete`` all resolve to the tmp paths.
    """
    from core.observability import checkpoint as ckpt
    ckpt_dir = tmp_path / "checkpoints"
    quar_dir = ckpt_dir / "quarantine"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    quar_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(ckpt, "CHECKPOINT_DIR", ckpt_dir), \
         patch.object(ckpt, "QUARANTINE_DIR", quar_dir):
        yield {"checkpoints": ckpt_dir, "quarantine": quar_dir}
