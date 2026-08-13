"""Tests for skills/cvm/screener/ — dashboard mode.

[v3] Simplified — only the error-path (no DB) + tab-structure tests remain.
The full dashboard() call is expensive; we call it exactly once per file.

The mock VAL_* data + `mock_all` fixture come from the screener conftest.
"""
from __future__ import annotations

import pytest

from skills.cvm.screener import MANIFEST, route


@pytest.fixture(autouse=True)
def _reset_seen_cnpjs():
    """Reset the module-level _seen_cnpjs set before each test.

    The screener's concurrent sector mode uses a module-level set for CNPJ
    dedup. dashboard() calls compare() which calls sector() internally,
    so the same leak applies.
    """
    from skills.cvm.screener.modes import sector as sector_mod
    sector_mod._seen_cnpjs.clear()
from skills.cvm.screener.modes.dashboard import dashboard
from tests.skills.cvm.screener.conftest import (
    CAD_COMPANIES, BRIDGE_SUZB3, BRIDGE_KLBN11, VAL_SUZB3, VAL_KLBN11,
)


class TestDashboardMode:
    def test_dashboard_no_company(self):
        """Empty company -> status=error with 'company is required'.

        The dashboard short-circuits before any underlying skill is called.
        """
        r = dashboard()
        assert r["status"] == "error"
        assert "company is required" in r["error"]

    def test_dashboard_tab_structure(self, mock_all, monkeypatch):
        """Tabs are exactly ['Overview', 'Peers', 'Comparison']."""
        mock_all(monkeypatch, CAD_COMPANIES,
                 {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                 {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = dashboard(company="SUZB3")
        assert r["status"] == "ok"
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Peers", "Comparison"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1
