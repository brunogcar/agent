"""tests/skills/ddm/focus/test_dashboard.py - dashboard tests.

[v4] Rewritten — no hardcoded indicator names (accents), no subtabs
on indicator tabs, table found directly in sections.
"""
from __future__ import annotations

import os
os.environ.setdefault("CVM_SKIP_SYNC", "1")

_MOCK_OBS = [
    {"year": 2026, "indicator": "IPCA", "four_weeks_ago": "5,151%", "one_week_ago": "5,018%", "today": "5,023%", "comparison": "up", "respondents": 149, "ref_date": "2026-08-22"},
    {"year": 2027, "indicator": "IPCA", "four_weeks_ago": "4,200%", "one_week_ago": "4,223%", "today": "4,240%", "comparison": "up", "respondents": 148, "ref_date": "2026-08-22"},
    {"year": 2028, "indicator": "IPCA", "four_weeks_ago": "3,775%", "one_week_ago": "3,800%", "today": "3,800%", "comparison": "flat", "respondents": 122, "ref_date": "2026-08-22"},
    {"year": 2029, "indicator": "IPCA", "four_weeks_ago": "3,500%", "one_week_ago": "3,500%", "today": "3,500%", "comparison": "flat", "respondents": 114, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "Câmbio", "four_weeks_ago": "R$ 5,200", "one_week_ago": "R$ 5,200", "today": "R$ 5,200", "comparison": "flat", "respondents": 119, "ref_date": "2026-08-22"},
    {"year": 2027, "indicator": "Câmbio", "four_weeks_ago": "R$ 5,278", "one_week_ago": "R$ 5,280", "today": "R$ 5,287", "comparison": "up", "respondents": 118, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "Selic", "four_weeks_ago": "14,000%", "one_week_ago": "13,750%", "today": "13,750%", "comparison": "flat", "respondents": 148, "ref_date": "2026-08-22"},
    {"year": 2029, "indicator": "Selic", "four_weeks_ago": "10,000%", "one_week_ago": "10,000%", "today": "10,000%", "comparison": "flat", "respondents": 112, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "Conta corrente", "four_weeks_ago": "US$ -60,000", "one_week_ago": "US$ -60,000", "today": "US$ -60,000", "comparison": "flat", "respondents": 42, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "Balança comercial", "four_weeks_ago": "US$ 76,200", "one_week_ago": "US$ 76,900", "today": "US$ 77,900", "comparison": "up", "respondents": 43, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "PIB Total", "four_weeks_ago": "1,986%", "one_week_ago": "1,983%", "today": "1,982%", "comparison": "down", "respondents": 116, "ref_date": "2026-08-22"},
    {"year": 2026, "indicator": "IGP-M", "four_weeks_ago": "4,500%", "one_week_ago": "4,400%", "today": "4,350%", "comparison": "down", "respondents": 80, "ref_date": "2026-08-22"},
]

_MOCK_SUMMARY = {
    "status": "ok",
    "ref_date": "2026-08-22",
    "years": [2026, 2027, 2028, 2029],
    "indicators": ["IPCA", "PIB Total", "Câmbio", "Selic", "IGP-M", "Conta corrente", "Balança comercial"],
    "total_observations": len(_MOCK_OBS),
}


def _patch_query(monkeypatch):
    """Mock query_engine so no DB access."""
    def _mock_all_data():
        return {"status": "ok", "observations": _MOCK_OBS, "ref_date": "2026-08-22"}
    def _mock_summary():
        return _MOCK_SUMMARY
    monkeypatch.setattr("data_sources.ddm.focus.query_engine.all_data", _mock_all_data)
    monkeypatch.setattr("data_sources.ddm.focus.query_engine.summary", _mock_summary)


class TestDashboard:
    def test_dashboard_has_13_tabs(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        assert res["status"] == "ok"
        assert len(res["tabs"]) == 13

    def test_dashboard_focus_tab_group(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        assert res["tabs"][0]["name"] == "Focus"
        assert res["tabs"][0]["group"] == "Boletim"

    def test_dashboard_indicator_tabs_group(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        for tab in res["tabs"][1:]:
            assert tab["group"] == "Indicadores"

    def test_focus_tab_has_4_year_subtabs(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        focus = res["tabs"][0]
        subtabs = [s for s in focus["sections"] if s.get("type") == "subtabs"]
        assert len(subtabs) == 1
        names = [s["name"] for s in subtabs[0]["tabs"]]
        assert "2026" in names

    def test_indicator_tab_has_no_subtabs(self, monkeypatch):
        """[v2] Indicator tabs no longer have subtabs."""
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        ipca = res["tabs"][1]
        subtabs = [s for s in ipca["sections"] if s.get("type") == "subtabs"]
        assert len(subtabs) == 0

    def test_indicator_tab_has_chart(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        ipca = res["tabs"][1]
        charts = [s for s in ipca["sections"] if s.get("type") == "chart"]
        assert len(charts) == 1

    def test_kpis_at_top_level(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        assert "kpis" in res
        assert len(res["kpis"]) >= 1

    def test_year_table_is_sortable(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        focus = res["tabs"][0]
        subtabs = next(s for s in focus["sections"] if s.get("type") == "subtabs")
        table = next(s for s in subtabs["tabs"][0]["sections"] if s.get("type") == "table")
        assert table.get("sortable") is True

    def test_year_table_has_negative_red(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        focus = res["tabs"][0]
        subtabs = next(s for s in focus["sections"] if s.get("type") == "subtabs")
        table = next(s for s in subtabs["tabs"][0]["sections"] if s.get("type") == "table")
        assert table.get("negative_red") is True

    def test_indicator_table_is_sortable(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        ipca = res["tabs"][1]
        table = next(s for s in ipca["sections"] if s.get("type") == "table")
        assert table.get("sortable") is True

    def test_indicator_table_has_negative_red(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        ipca = res["tabs"][1]
        table = next(s for s in ipca["sections"] if s.get("type") == "table")
        assert table.get("negative_red") is True

    def test_indicator_chart_has_3_datasets(self, monkeypatch):
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        ipca = res["tabs"][1]
        chart = next(s for s in ipca["sections"] if s.get("type") == "chart")
        assert len(chart["chart_data"]["data"]["datasets"]) == 3

    def test_indicator_chart_parses_currency(self, monkeypatch):
        """[v4] Câmbio chart should have numeric values (5200, not None)."""
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        cambio = next(t for t in res["tabs"] if t["name"] == "Câmbio")
        chart = next(s for s in cambio["sections"] if s.get("type") == "chart")
        # First dataset (four_weeks_ago), first data point (2026)
        val = chart["chart_data"]["data"]["datasets"][0]["data"][0]
        assert val is not None
        assert val == 5200.0

    def test_indicator_chart_parses_us_dollar(self, monkeypatch):
        """[v4] Conta corrente chart should have numeric values (US$)."""
        _patch_query(monkeypatch)
        from skills.ddm.focus.modes import dashboard
        res = dashboard.dashboard()
        cc = next(t for t in res["tabs"] if "Conta" in t["name"])
        chart = next(s for s in cc["sections"] if s.get("type") == "chart")
        val = chart["chart_data"]["data"]["datasets"][0]["data"][0]
        assert val is not None
        assert val == -60000.0
