"""Shared fixtures for backtest tests."""
from __future__ import annotations
import os

os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
