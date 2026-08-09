"""Shared fixtures for CVM skill tests.

Sets environment variables required by core.config to prevent
RuntimeError: PLANNER_MODEL is required in .env during test collection.

IMPORTANT: env vars are set at MODULE LEVEL (not in a fixture) using
os.environ.setdefault(). This ensures they are set BEFORE core.config
is imported (which happens at first import, not at test time). Using
monkeypatch.setenv in a fixture would set them only during the test,
but core.config is a singleton -- once initialized, it doesn't re-read
env vars. This would cause the singleton to retain test values after
the fixture restores the original env vars, leaking state to other
test directories (e.g., autoresearch tests would see PLANNER_PROVIDER=test).

setdefault() ensures:
  - Env vars are set before any test runs (at conftest import time)
  - core.config initializes consistently across all tests
  - Existing env vars are NOT overridden (if the user has real values)
  - No monkeypatch scoping issues -- the singleton is stable

[v2] Added `mock_freshness` autouse fixture — mocks
skills.cvm._freshness.get_freshness so no test opens real SQLite DBs
to check sync timestamps. Without this, every CVM skill mode that calls
add_freshness() (insider, governance, historical, etc.) opens 9 SQLite
databases per call, making tests take 2+ minutes on a machine with real
data. The mock returns a dummy dict so data_freshness is still present
in results.
"""
from __future__ import annotations
import os

import pytest

# Set env vars at module level (before any test or core.config import).
# setdefault = don't override if already set by the user.
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")

# [v1.14] Disable sync guard for ALL CVM tests. Tests use synthetic DBs —
# they must NOT trigger real syncs (which download gigabytes + take minutes).
# Individual tests that need to exercise the sync guard set CVM_SKIP_SYNC=0
# locally + mock the sync functions.
os.environ.setdefault("CVM_SKIP_SYNC", "1")

# [v5] Disable auto-HTML generation for ALL CVM tests. Dashboard mode now
# auto-generates an HTML file on every route() call — tests don't need this
# (it slows tests + creates files). Individual tests that need HTML set
# CVM_SKIP_HTML=0 locally.
os.environ.setdefault("CVM_SKIP_HTML", "1")


@pytest.fixture(autouse=True)
def mock_freshness(monkeypatch):
    """[v3] Mock add_freshness directly so no test opens real SQLite DBs.

    add_freshness() calls get_freshness() which opens 9 SQLite databases
    (dfp, itr, fre, ipe, cad, vlmo, cgvn, fca, bridge) to read sync_state
    timestamps. On a machine with real databases, each call takes 100-500ms.
    With 30+ tests calling modes that use add_freshness, this adds 10-30
    seconds of pure DB-open overhead.

    [v3] Instead of mocking get_freshness (v2 approach — still slow because
    add_freshness itself runs), we mock add_freshness entirely as a no-op
    that still injects the data_freshness key so tests that check for it
    pass. This is MUCH faster because it skips the entire function body.
    """
    _dummy_freshness = {
        "dfp": "", "itr": "", "fre": "", "ipe": "",
        "cad": "", "vlmo": "", "cgvn": "", "fca": "", "bridge": "",
    }
    def _fake_add_freshness(result):
        if isinstance(result, dict):
            result["data_freshness"] = _dummy_freshness
        return result
    monkeypatch.setattr("skills.cvm._freshness.add_freshness", _fake_add_freshness)
