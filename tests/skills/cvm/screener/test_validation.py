"""Tests for skills/cvm/screener/ — input validation across all modes.

[Phase 4] Split out of the original single-file `test_screener.py`.
Covers validation behavior for sector + compare modes:
  - missing `setor` arg → error
  - missing `company` arg → error

These tests don't need the mock_all fixture because validation short-
circuits before any underlying skill is called.
"""
from __future__ import annotations

from skills.cvm.screener.modes.sector import sector
from skills.cvm.screener.modes.compare import compare


class TestValidation:
    def test_sector_requires_setor(self):
        r = sector()
        assert r["status"] == "error"
        assert "setor" in r["error"]

    def test_compare_requires_company(self):
        r = compare()
        assert r["status"] == "error"
        assert "company" in r["error"]
