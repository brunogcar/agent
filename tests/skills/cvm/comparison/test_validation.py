"""Tests for skills/cvm/comparison/ — input validation across all modes.

[Phase 4] Split out of the original single-file `test_comparison.py`.
Covers validation behavior for side_by_side + summary + growth modes:
  - missing `tickers` arg → error
  - `tickers` not a list → error
  - `tickers` has fewer than 2 entries → error

These tests don't need the mock_skills fixture because validation short-
circuits before any underlying skill is called.
"""
from __future__ import annotations

from skills.cvm.comparison import comparison


class TestValidation:
    def test_side_by_side_requires_tickers(self):
        r = comparison.side_by_side()
        assert r["status"] == "error"
        assert "tickers" in r["error"]

    def test_side_by_side_requires_list(self):
        r = comparison.side_by_side(tickers="PETR4")
        assert r["status"] == "error"

    def test_side_by_side_requires_min_two(self):
        r = comparison.side_by_side(tickers=["PETR4"])
        assert r["status"] == "error"
        assert "2 tickers" in r["error"]

    def test_summary_requires_tickers(self):
        r = comparison.summary()
        assert r["status"] == "error"

    def test_summary_requires_min_two(self):
        r = comparison.summary(tickers=["PETR4"])
        assert r["status"] == "error"
