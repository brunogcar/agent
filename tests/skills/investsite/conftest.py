"""Shared fixtures for investsite skill tests.

Sets environment variables required by core.config to prevent
RuntimeError: PLANNER_MODEL is required in .env during test collection.
Mirrors tests/skills/cvm/conftest.py — investsite is a top-level domain
(not under cvm/), so it needs its own conftest to set the env vars before
any test imports core.config (which historical.py imports via
calculations.engines via data_sources.cvm._db).

Env vars are set at MODULE LEVEL (not in a fixture) using
os.environ.setdefault(). This ensures they are set BEFORE core.config is
imported. See tests/skills/cvm/conftest.py for the full rationale.
"""
from __future__ import annotations
import os

# Set env vars at module level (before any test or core.config import).
# setdefault = don't override if already set by the user.
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")

# [v5] Disable auto-HTML generation for investsite tests (same as CVM tests).
os.environ.setdefault("CVM_SKIP_HTML", "1")
