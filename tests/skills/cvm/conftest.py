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
skills._freshness.get_freshness so no test opens real SQLite DBs
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

# [engine-cache] Disable DB engine cache for ALL CVM tests. The cache
# persists engine results to memory_db/cache/engine_cache.db — tests use
# synthetic DBs and shouldn't read/write the persistent cache. Individual
# tests that need the DB cache set CVM_SKIP_DB_CACHE=0 locally.
os.environ.setdefault("CVM_SKIP_DB_CACHE", "1")


@pytest.fixture(autouse=True)
def mock_freshness(monkeypatch):
    """[v4] Mock get_freshness + get_last_synced_period so add_freshness
    doesn't open real SQLite DBs.

    The v3 approach patched ``add_freshness`` itself at
    ``skills._freshness.add_freshness``. This worked for modules that
    imported it inside a function body (``from skills._freshness import
    add_freshness`` re-imports at call time → sees the patch), but NOT
    for modules that imported it at MODULE LEVEL (e.g.
    ``skills/cvm/historical/helpers.py``,
    ``skills/cvm/historical/modes/summary.py``). A module-level ``from
    ... import`` creates a local binding that points to the ORIGINAL
    function object; patching the source module's attribute doesn't
    update the already-bound reference. This caused every historical
    test to call the REAL add_freshness → get_freshness, which opens
    ~15 SQLite DBs (CVM+B3+BCB+DDM), adding ~1.5s per test.

    [v4] Instead of patching add_freshness, we patch get_freshness and
    get_last_synced_period — the two functions add_freshness calls
    internally. These are resolved by bare name from
    ``skills._freshness.__dict__`` at CALL TIME (Python global lookup),
    so the patch is effective regardless of how/where add_freshness was
    imported.
    """
    _dummy_freshness = {
        "dfp": "", "itr": "", "fre": "", "ipe": "",
        "cad": "", "vlmo": "", "cgvn": "", "fca": "", "bridge": "",
    }
    monkeypatch.setattr("skills._freshness.get_freshness", lambda: _dummy_freshness)
    monkeypatch.setattr("skills._freshness.get_last_synced_period", lambda: {})
