"""Tests for skills/cvm/screener/ — sector screener skill.

Uses mocked CAD + bridge + valuation so no database/network is needed.
"""
from __future__ import annotations

import pytest

from skills.cvm.screener import screener


# ── Synthetic data ───────────────────────────────────────────────────────────

CAD_COMPANIES = [
    {"CD_CVM": "13986", "CNPJ_CIA": "16404287000155",
     "DENOM_COMERC": "SUZANO", "DENOM_SOCIAL": "SUZANO S.A.", "SETOR_ATIV": "Papel e Celulose"},
    {"CD_CVM": "12653", "CNPJ_CIA": "89637490000145",
     "DENOM_COMERC": "KLABIN", "DENOM_SOCIAL": "KLABIN S.A.", "SETOR_ATIV": "Papel e Celulose"},
]

BRIDGE_SUZB3 = {"status": "ok", "ticker": "SUZB3", "cnpj": "16404287000155", "cd_cvm": "13986"}
BRIDGE_KLBN11 = {"status": "ok", "ticker": "KLBN11", "cnpj": "89637490000145", "cd_cvm": "12653"}

VAL_SUZB3 = {"status": "ok", "ticker": "SUZB3", "ratios": {
    "price": 42.0, "market_cap": 53_000_000_000, "p_l": 4.0, "p_vpa": 1.2,
    "ev_ebitda": 6.0, "dividend_yield": 0.25, "lucro_liquido": 13_000_000_000,
    "patrimonio_liquido": 44_000_000_000}}
VAL_KLBN11 = {"status": "ok", "ticker": "KLBN11", "ratios": {
    "price": 17.0, "market_cap": 22_000_000_000, "p_l": 13.0, "p_vpa": 7.0,
    "ev_ebitda": 20.0, "dividend_yield": 0.015, "lucro_liquido": 1_700_000_000,
    "patrimonio_liquido": 14_400_000_000}}


def _mock_all(monkeypatch, cad_comps, bridge_map, val_map):
    """Mock CAD search, bridge lookup, valuation ratios."""
    def fake_cad_search(setor="", **kwargs):
        return {"status": "ok",
                "companies": [c for c in cad_comps if setor.lower() in c.get("SETOR_ATIV","").lower()]}
    def fake_bridge_lookup(ticker="", cd_cvm="", cnpj=""):
        if ticker:
            return bridge_map.get(ticker, {"status": "not_found"})
        if cd_cvm:
            for t, r in bridge_map.items():
                if r.get("cd_cvm") == cd_cvm:
                    return r
            return {"status": "not_found"}
        return {"status": "not_found"}
    def fake_val_ratios(company=""):
        return val_map.get(company, {"status": "error", "error": "no data"})
    def fake_cad_lookup(cnpj="", cd_cvm="", name=""):
        for c in cad_comps:
            if cnpj and c.get("CNPJ_CIA","").replace(".","").replace("/","").replace("-","") == cnpj.replace(".","").replace("/","").replace("-",""):
                return {"status": "ok", "company": c}
            if cd_cvm and c.get("CD_CVM") == cd_cvm:
                return {"status": "ok", "company": c}
        return {"status": "not_found"}

    monkeypatch.setattr("data_sources.cvm.cad.query_engine.search", fake_cad_search)
    monkeypatch.setattr("data_sources.cvm.cad.query_engine.lookup", fake_cad_lookup)
    monkeypatch.setattr("data_sources.cvm.bridge.query_engine.lookup", fake_bridge_lookup)
    monkeypatch.setattr("skills.cvm.valuation.modes.ratios.ratios", fake_val_ratios)


# ── Input validation ─────────────────────────────────────────────────────────

class TestValidation:
    def test_sector_requires_setor(self):
        r = screener.sector()
        assert r["status"] == "error"
        assert "setor" in r["error"]

    def test_compare_requires_company(self):
        r = screener.compare()
        assert r["status"] == "error"
        assert "company" in r["error"]


# ── sector mode ──────────────────────────────────────────────────────────────

class TestSectorMode:
    def test_basic_shape(self, monkeypatch):
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel e Celulose")
        assert r["status"] == "ok"
        assert r["setor"] == "Papel e Celulose"
        assert r["peer_count"] == 2
        assert len(r["peers"]) == 2
        assert "medians" in r

    def test_peers_sorted_by_pl_cheapest_first(self, monkeypatch):
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel")
        # SUZB3 P/L=4.0, KLBN11 P/L=13.0 → SUZB3 first (cheapest)
        assert r["peers"][0]["ticker"] == "SUZB3"
        assert r["peers"][1]["ticker"] == "KLBN11"

    def test_medians_computed(self, monkeypatch):
        _mock_all(monkeypng=monkeypatch, cad_comps=CAD_COMPANIES,
                  bridge_map={"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  val_map={"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11}) if False else None
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.sector(setor="Papel")
        # median of [4.0, 13.0] = 8.5
        assert r["medians"]["p_l"] == 8.5
        # median of [0.25, 0.015] = 0.1325
        assert r["medians"]["dividend_yield"] == pytest.approx(0.1325)

    def test_no_companies_found(self, monkeypatch):
        _mock_all(monkeypatch, [], {}, {})
        r = screener.sector(setor="Nonexistent")
        assert r["status"] == "not_found"

    def test_skips_companies_without_ticker(self, monkeypatch):
        """Companies in CAD but not in bridge are skipped (not an error)."""
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3},  # KLBN11 not in bridge
                  {"SUZB3": VAL_SUZB3})
        r = screener.sector(setor="Papel")
        assert r["status"] == "ok"
        assert r["peer_count"] == 1  # only SUZB3


# ── compare mode ─────────────────────────────────────────────────────────────

class TestCompareMode:
    def test_basic_shape(self, monkeypatch):
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.compare(company="SUZB3")
        assert r["status"] == "ok"
        assert r["ticker"] == "SUZB3"
        assert r["setor"] == "Papel e Celulose"
        assert "comparison" in r
        assert "my_data" in r
        assert "medians" in r

    def test_comparison_shows_cheap_or_expensive(self, monkeypatch):
        _mock_all(monkeypatch, CAD_COMPANIES,
                  {"SUZB3": BRIDGE_SUZB3, "KLBN11": BRIDGE_KLBN11},
                  {"SUZB3": VAL_SUZB3, "KLBN11": VAL_KLBN11})
        r = screener.compare(company="SUZB3")
        comp = r["comparison"]
        # SUZB3 P/L=4.0, median=8.5 → cheap
        assert comp["p_l"]["vs_sector"] == "cheap"
        # SUZB3 ROE = 13B/44B = 0.295, KLBN11 ROE = 1.7B/14.4B = 0.118, median = 0.207
        # SUZB3 ROE > median → "above"
        assert comp["roe"]["vs_sector"] == "above"

    def test_ticker_not_in_bridge(self, monkeypatch):
        _mock_all(monkeypatch, CAD_COMPANIES, {}, {})
        r = screener.compare(company="UNKNOWN4")
        assert r["status"] == "not_found"


# ── Route dispatch ───────────────────────────────────────────────────────────

class TestRoute:
    def test_route_no_mode_errors(self):
        from skills.cvm.screener import route
        r = route()
        assert r["status"] == "error"

    def test_route_unknown_mode_errors(self):
        from skills.cvm.screener import route
        r = route(mode="nope")
        assert r["status"] == "error"
        assert "Unknown mode" in r["error"]
