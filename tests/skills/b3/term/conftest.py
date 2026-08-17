"""Shared fixtures for the b3.term skill tests.

No synthetic DB needed — the dashboard uses graceful degradation.
When no DB is available, tabs get error sections but the dashboard
still returns status=ok with 3 tabs.
"""
from __future__ import annotations

import os

os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_HTML", "1")
