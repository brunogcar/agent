"""Shared fixtures for B3 data source tests.

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
"""
from __future__ import annotations
import os

# Set env vars at module level (before any test or core.config import).
# setdefault = don't override if already set by the user.
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
