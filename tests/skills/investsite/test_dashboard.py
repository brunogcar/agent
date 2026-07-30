"""Tests for skills/investsite/ — dashboard mode.

[v1.1] Split out of the original single-file `test_investsite.py`.
Covers the dashboard mode (multi-tab composition that orchestrates the
underlying indicators + events modes):

  - no ticker -> short-circuit error
  - basic shape (status, tabs, kpis lists)
  - tab names exactly ['Overview', 'Key Indicators', 'Latest Events']
  - top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield)
  - degradation when indicators() + events() raise ConnectionError
    (3 tabs + all KPIs as '—')
  - route dispatches to dashboard mode

The mock setup patches `fetch_page` (imported into modes/indicators.py +
modes/events.py) + `parse_indicators` / `parse_events` so dashboard()
doesn't hit the network or parse real HTML.
"""
from __future__ import annotations

from skills.investsite import MANIFEST, route
from skills.investsite.modes.dashboard import dashboard


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_fetches(monkeypatch):
    """Mock fetch_page + parse_indicators + parse_events to return synthetic
    data so dashboard() doesn't hit the network.

    Patches the local references in modes/indicators.py + modes/events.py
    (the dashboard's underlying sub-modes) — the same paths the degraded
    test patches to raise ConnectionError.
    """
    def fake_fetch_page(path, params=None, force=False):
        return "<html></html>"  # Raw HTML — content doesn't matter, parsers are mocked.

    def fake_parse_indicators(html):
        return {
            "status": "ok",
            "ticker": "PETR4",
            "sections": {
                "dados_basicos": {"Empresa": "PETROBRAS"},
                "precos_relativos": {
                    "Preco/Lucro": 8.5,
                    "Preco/VPA": 1.9,
                    "EV/EBITDA": 4.5,
                    "Dividend Yield": 0.12,
                },
                "retornos_margens": {
                    "Retorno s/ Patrimonio Liquido": 0.25,
                },
            },
        }

    def fake_parse_events(html, categoria=""):
        return {
            "status": "ok",
            "ticker": "PETR4",
            "events": [
                {"data": "2024-06-15", "categoria": "Fato Relevante",
                 "descricao": "Test event", "link": "https://example.com"},
            ],
        }

    monkeypatch.setattr("skills.investsite.modes.indicators.fetch_page", fake_fetch_page)
    monkeypatch.setattr("skills.investsite.modes.events.fetch_page", fake_fetch_page)
    monkeypatch.setattr("skills.investsite.modes.indicators.parse_indicators", fake_parse_indicators)
    monkeypatch.setattr("skills.investsite.modes.events.parse_events", fake_parse_events)


class TestDashboardMode:
    def test_dashboard_no_ticker(self):
        """Empty ticker -> status=error with 'ticker is required'.

        The dashboard short-circuits before any HTTP fetch is attempted.
        """
        r = dashboard()
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]

    def test_dashboard_basic_shape(self, monkeypatch):
        """Dashboard returns status=ok with top-level tabs + kpis lists."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert r["status"] == "ok"
        assert "tabs" in r
        assert "kpis" in r
        assert isinstance(r["tabs"], list)
        assert isinstance(r["kpis"], list)

    def test_dashboard_tab_names(self, monkeypatch):
        """Tabs are exactly ['Overview', 'Key Indicators', 'Latest Events']."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        names = [t["name"] for t in r["tabs"]]
        assert names == ["Overview", "Key Indicators", "Latest Events"]
        # Each tab has a non-empty sections list.
        for t in r["tabs"]:
            assert isinstance(t["sections"], list)
            assert len(t["sections"]) >= 1

    def test_dashboard_top_level_kpis(self, monkeypatch):
        """5 KPI cards at the top level with exact labels + unit fields."""
        _mock_fetches(monkeypatch)
        r = dashboard(ticker="PETR4")
        assert len(r["kpis"]) == 5
        labels = [k["label"] for k in r["kpis"]]
        assert labels == ["P/L", "P/VPA", "EV/EBITDA", "ROE", "Dividend Yield"]
        # Each KPI has label + value + unit.
        for k in r["kpis"]:
            assert "label" in k
            assert "value" in k
            assert "unit" in k

    def test_dashboard_degrades_when_sub_calls_fail(self, monkeypatch):
        """When indicators() + events() BOTH return error payloads (e.g.
        ConnectionError), the dashboard still renders status=ok with 3 tabs +
        all KPIs as '—'."""
        def boom(*args, **kwargs):
            raise ConnectionError("Network error")
        monkeypatch.setattr("skills.investsite.modes.indicators.fetch_page", boom)
        monkeypatch.setattr("skills.investsite.modes.events.fetch_page", boom)
        r = dashboard(ticker="PETR4")
        assert r["status"] == "ok"
        assert len(r["tabs"]) == 3
        # All 5 KPIs render as "—" (no data).
        for k in r["kpis"]:
            assert k["value"] == "—"
        # All tabs have a section (tables have 0 rows; Overview text shows "—").
        for t in r["tabs"]:
            assert len(t["sections"]) >= 1

    def test_route_dispatches_dashboard_mode(self, monkeypatch):
        """route(mode='dashboard') with no ticker returns status=error with
        'ticker is required'."""
        _mock_fetches(monkeypatch)
        assert "dashboard" in MANIFEST["modes"]
        r = route(mode="dashboard")
        assert r["status"] == "error"
        assert "ticker is required" in r["error"]
